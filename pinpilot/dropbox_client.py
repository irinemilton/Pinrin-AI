"""
PinPilot Dropbox Client

Handles fetching product files, listing product folders,
downloading images, reading product metadata, and moving
processed files to the published folder.
"""

import json
import logging
import tempfile
from pathlib import Path
from typing import Any

import dropbox
from dropbox.files import FileMetadata, FolderMetadata
from dropbox.exceptions import ApiError

from .config import DropboxConfig

logger = logging.getLogger("pinpilot.dropbox")


class ProductFolder:
    """Represents a product folder in Dropbox with its metadata and images."""

    def __init__(self, folder_path: str, metadata: dict[str, Any], image_paths: list[str]):
        self.folder_path = folder_path
        self.name = Path(folder_path).name
        self.metadata = metadata
        self.image_paths = image_paths

    @property
    def title(self) -> str:
        return self.metadata.get("title", self.name.replace("-", " ").title())

    @property
    def description(self) -> str:
        return self.metadata.get("description", "")

    @property
    def gumroad_url(self) -> str:
        return self.metadata.get("gumroad_url", "")

    @property
    def tags(self) -> list[str]:
        return self.metadata.get("tags", [])

    @property
    def board(self) -> str:
        return self.metadata.get("board", "")

    @property
    def price(self) -> str:
        return self.metadata.get("price", "")

    @property
    def variations(self) -> list[dict[str, str]]:
        return self.metadata.get("variations", [])

    def __repr__(self) -> str:
        return f"ProductFolder(name={self.name!r}, images={len(self.image_paths)}, variations={len(self.variations)})"


class DropboxClient:
    """Client for interacting with Dropbox to manage product assets."""

    def __init__(self, config: DropboxConfig):
        self.config = config
        self._dbx: dropbox.Dropbox | None = None

    @property
    def dbx(self) -> dropbox.Dropbox:
        """Lazy-initialize Dropbox client."""
        if self._dbx is None:
            if not self.config.is_configured:
                raise RuntimeError(
                    "Dropbox is not configured. Set DROPBOX_ACCESS_TOKEN in your .env file."
                )
            self._dbx = dropbox.Dropbox(self.config.access_token)
            # Verify connection
            try:
                account = self._dbx.users_get_current_account()
                logger.info(f"Connected to Dropbox as: {account.name.display_name}")
            except Exception as e:
                self._dbx = None
                raise RuntimeError(f"Failed to connect to Dropbox: {e}")
        return self._dbx

    def list_product_folders(self) -> list[str]:
        """List all product folders in the products directory.

        Returns:
            List of folder paths relative to Dropbox root.
        """
        try:
            result = self.dbx.files_list_folder(self.config.products_path)
        except ApiError as e:
            if e.error.is_path() and e.error.get_path().is_not_found():
                logger.warning(f"Products folder not found: {self.config.products_path}")
                logger.info("Create the folder in Dropbox and add your product subfolders.")
                return []
            raise

        folders = []
        for entry in result.entries:
            if isinstance(entry, FolderMetadata):
                folders.append(entry.path_display)

        # Handle pagination
        while result.has_more:
            result = self.dbx.files_list_folder_continue(result.cursor)
            for entry in result.entries:
                if isinstance(entry, FolderMetadata):
                    folders.append(entry.path_display)

        logger.info(f"Found {len(folders)} product folder(s)")
        return sorted(folders)

    def read_product_metadata(self, folder_path: str) -> dict[str, Any]:
        """Read product.json from a product folder.

        Args:
            folder_path: Dropbox path to the product folder.

        Returns:
            Parsed product metadata dictionary.
        """
        metadata_path = f"{folder_path}/product.json"
        try:
            _, response = self.dbx.files_download(metadata_path)
            content = response.content.decode("utf-8")
            metadata = json.loads(content)
            logger.debug(f"Loaded metadata from: {metadata_path}")
            return metadata
        except ApiError as e:
            if e.error.is_path() and e.error.get_path().is_not_found():
                logger.warning(f"No product.json found in: {folder_path}")
                return {}
            raise
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON in {metadata_path}: {e}")
            return {}

    def list_images(self, folder_path: str) -> list[str]:
        """List all image files in a product folder.

        Args:
            folder_path: Dropbox path to the product folder.

        Returns:
            List of image file paths.
        """
        image_extensions = {".png", ".jpg", ".jpeg", ".webp"}
        try:
            result = self.dbx.files_list_folder(folder_path)
        except ApiError:
            return []

        images = []
        for entry in result.entries:
            if isinstance(entry, FileMetadata):
                ext = Path(entry.name).suffix.lower()
                if ext in image_extensions:
                    images.append(entry.path_display)

        # Handle pagination
        while result.has_more:
            result = self.dbx.files_list_folder_continue(result.cursor)
            for entry in result.entries:
                if isinstance(entry, FileMetadata):
                    ext = Path(entry.name).suffix.lower()
                    if ext in image_extensions:
                        images.append(entry.path_display)

        return sorted(images)

    def download_image(self, image_path: str, local_dir: str | Path | None = None) -> Path:
        """Download an image file from Dropbox to a local path.

        Args:
            image_path: Dropbox path to the image.
            local_dir: Optional local directory to save to. Uses temp dir if None.

        Returns:
            Path to the downloaded local file.
        """
        if local_dir is None:
            local_dir = Path(tempfile.mkdtemp(prefix="pinpilot_"))
        else:
            local_dir = Path(local_dir)
            local_dir.mkdir(parents=True, exist_ok=True)

        filename = Path(image_path).name
        local_path = local_dir / filename

        _, response = self.dbx.files_download(image_path)
        local_path.write_bytes(response.content)

        logger.debug(f"Downloaded: {image_path} → {local_path}")
        return local_path

    def get_product(self, folder_path: str) -> ProductFolder:
        """Load a complete product from a Dropbox folder.

        Args:
            folder_path: Dropbox path to the product folder.

        Returns:
            A ProductFolder instance with metadata and image paths.
        """
        metadata = self.read_product_metadata(folder_path)
        images = self.list_images(folder_path)
        return ProductFolder(folder_path, metadata, images)

    def get_all_products(self) -> list[ProductFolder]:
        """Load all products from the products directory.

        Returns:
            List of ProductFolder instances.
        """
        folders = self.list_product_folders()
        products = []
        for folder_path in folders:
            product = self.get_product(folder_path)
            if product.image_paths:
                products.append(product)
            else:
                logger.warning(f"Skipping {folder_path}: no images found")
        return products

    def move_to_published(self, folder_path: str) -> str | None:
        """Move a product folder to the published directory.

        Args:
            folder_path: Dropbox path to the product folder.

        Returns:
            New path if successful, None if failed.
        """
        folder_name = Path(folder_path).name
        dest_path = f"{self.config.published_path}/{folder_name}"

        try:
            # Ensure published directory exists
            try:
                self.dbx.files_create_folder_v2(self.config.published_path)
            except ApiError:
                pass  # Folder already exists

            result = self.dbx.files_move_v2(folder_path, dest_path)
            new_path = result.metadata.path_display
            logger.info(f"Moved to published: {folder_path} → {new_path}")
            return new_path
        except ApiError as e:
            logger.error(f"Failed to move {folder_path}: {e}")
            return None

    def get_temporary_link(self, file_path: str) -> str | None:
        """Get a temporary download link for a file (valid for 4 hours).

        This is useful for providing image URLs to the Pinterest API.

        Args:
            file_path: Dropbox path to the file.

        Returns:
            Temporary URL string, or None if failed.
        """
        try:
            result = self.dbx.files_get_temporary_link(file_path)
            return result.link
        except ApiError as e:
            logger.error(f"Failed to get temp link for {file_path}: {e}")
            return None
