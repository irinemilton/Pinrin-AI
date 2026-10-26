"""
PinPilot Pinterest Client

Handles creating Pins, managing boards, uploading images,
and interacting with the Pinterest v5 API.
"""

import logging
import time
from pathlib import Path
from typing import Any

import requests

from .config import PinterestConfig

logger = logging.getLogger("pinpilot.pinterest")


class PinResult:
    """Result of a Pin creation attempt."""

    def __init__(
        self,
        success: bool,
        pin_id: str | None = None,
        pin_url: str | None = None,
        error: str | None = None,
        raw_response: dict | None = None,
    ):
        self.success = success
        self.pin_id = pin_id
        self.pin_url = pin_url
        self.error = error
        self.raw_response = raw_response or {}

    def __repr__(self) -> str:
        if self.success:
            return f"PinResult(success=True, pin_id={self.pin_id!r})"
        return f"PinResult(success=False, error={self.error!r})"


class PinterestClient:
    """Client for the Pinterest v5 API.

    Supports creating Pins with images (via URL or upload),
    listing boards, and checking Pin status.
    """

    def __init__(self, config: PinterestConfig):
        self.config = config
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Bearer {config.access_token}",
            "Content-Type": "application/json",
        })

    @property
    def base_url(self) -> str:
        return self.config.base_url

    def _request(
        self,
        method: str,
        endpoint: str,
        json_data: dict | None = None,
        files: dict | None = None,
        params: dict | None = None,
    ) -> dict[str, Any]:
        """Make an authenticated request to the Pinterest API.

        Args:
            method: HTTP method (GET, POST, etc.)
            endpoint: API endpoint path (e.g., "/pins")
            json_data: JSON body data
            files: File upload data
            params: URL query parameters

        Returns:
            Parsed JSON response.

        Raises:
            requests.HTTPError: If the API returns an error status.
        """
        url = f"{self.base_url}{endpoint}"

        # Remove Content-Type header when uploading files
        headers = dict(self.session.headers)
        if files:
            headers.pop("Content-Type", None)

        response = requests.request(
            method=method,
            url=url,
            headers=headers,
            json=json_data,
            files=files,
            params=params,
            timeout=30,
        )

        if response.status_code == 429:
            # Rate limited — wait and retry once
            retry_after = int(response.headers.get("Retry-After", 60))
            logger.warning(f"Rate limited. Waiting {retry_after}s before retry...")
            time.sleep(retry_after)
            response = requests.request(
                method=method,
                url=url,
                headers=headers,
                json=json_data,
                files=files,
                params=params,
                timeout=30,
            )

        if not response.ok:
            logger.error(
                f"Pinterest API error: {response.status_code} — {response.text}"
            )
            response.raise_for_status()

        return response.json()

    def verify_connection(self) -> dict[str, Any] | None:
        """Verify the Pinterest API connection by fetching user info.

        Returns:
            User account data if successful, None if failed.
        """
        if not self.config.is_configured:
            logger.error("Pinterest is not configured. Set access token and board ID.")
            return None

        try:
            data = self._request("GET", "/user_account")
            username = data.get("username", "unknown")
            logger.info(f"Connected to Pinterest as: {username}")
            return data
        except Exception as e:
            logger.error(f"Failed to connect to Pinterest: {e}")
            return None

    def list_boards(self) -> list[dict[str, Any]]:
        """List all boards for the authenticated user.

        Returns:
            List of board objects with id, name, description, etc.
        """
        boards = []
        bookmark = None

        while True:
            params = {"page_size": 25}
            if bookmark:
                params["bookmark"] = bookmark

            data = self._request("GET", "/boards", params=params)
            boards.extend(data.get("items", []))

            bookmark = data.get("bookmark")
            if not bookmark:
                break

        logger.info(f"Found {len(boards)} board(s)")
        return boards

    def find_board_by_name(self, name: str) -> dict[str, Any] | None:
        """Find a board by name (case-insensitive).

        Args:
            name: Board name to search for.

        Returns:
            Board object if found, None otherwise.
        """
        boards = self.list_boards()
        for board in boards:
            if board.get("name", "").lower() == name.lower():
                return board
        return None

    def create_board(self, name: str, description: str = "") -> dict[str, Any]:
        """Create a new board.

        Args:
            name: Board name.
            description: Optional board description.

        Returns:
            Created board object.
        """
        data = {
            "name": name,
            "description": description,
            "privacy": "PUBLIC",
        }
        result = self._request("POST", "/boards", json_data=data)
        logger.info(f"Created board: {result.get('name')} (ID: {result.get('id')})")
        return result

    def get_or_create_board(self, name: str, description: str = "") -> str:
        """Get a board ID by name, creating it if it doesn't exist.

        Args:
            name: Board name.
            description: Description for new board if created.

        Returns:
            Board ID string.
        """
        board = self.find_board_by_name(name)
        if board:
            board_id = board["id"]
            logger.debug(f"Using existing board: {name} (ID: {board_id})")
            return board_id

        board = self.create_board(name, description)
        board_id = board["id"]
        logger.info(f"Created new board: {name} (ID: {board_id})")
        return board_id

    def create_pin_from_url(
        self,
        title: str,
        description: str,
        image_url: str,
        link: str,
        board_id: str | None = None,
        alt_text: str = "",
    ) -> PinResult:
        """Create a Pin using an image URL.

        This is the primary method — it uses a publicly accessible image URL
        (e.g., a Dropbox temporary link) to create the Pin.

        Args:
            title: Pin title (max 100 chars).
            description: Pin description (max 500 chars).
            image_url: URL to the Pin image.
            link: Destination URL when the Pin is clicked (your Gumroad page).
            board_id: Target board ID. Uses default from config if None.
            alt_text: Alt text for accessibility.

        Returns:
            PinResult with success status and Pin details.
        """
        board_id = board_id or self.config.board_id

        # Truncate to API limits
        title = title[:100]
        description = description[:500]

        pin_data = {
            "title": title,
            "description": description,
            "board_id": board_id,
            "link": link,
            "media_source": {
                "source_type": "image_url",
                "url": image_url,
            },
        }

        if alt_text:
            pin_data["alt_text"] = alt_text[:500]

        try:
            result = self._request("POST", "/pins", json_data=pin_data)
            pin_id = result.get("id", "")
            pin_url = f"https://www.pinterest.com/pin/{pin_id}/"

            logger.info(f"✅ Pin created: {title[:50]}... → {pin_url}")
            return PinResult(
                success=True,
                pin_id=pin_id,
                pin_url=pin_url,
                raw_response=result,
            )

        except requests.HTTPError as e:
            error_msg = str(e)
            logger.error(f"❌ Failed to create Pin: {error_msg}")
            return PinResult(success=False, error=error_msg)

        except Exception as e:
            error_msg = f"Unexpected error: {e}"
            logger.error(f"❌ {error_msg}")
            return PinResult(success=False, error=error_msg)

    def create_pin_from_file(
        self,
        title: str,
        description: str,
        image_path: str | Path,
        link: str,
        board_id: str | None = None,
        alt_text: str = "",
    ) -> PinResult:
        """Create a Pin by uploading an image file directly.

        Use this as a fallback if the image URL method doesn't work.

        Args:
            title: Pin title (max 100 chars).
            description: Pin description (max 500 chars).
            image_path: Local path to the image file.
            link: Destination URL when the Pin is clicked.
            board_id: Target board ID. Uses default from config if None.
            alt_text: Alt text for accessibility.

        Returns:
            PinResult with success status and Pin details.
        """
        board_id = board_id or self.config.board_id
        image_path = Path(image_path)

        if not image_path.exists():
            return PinResult(success=False, error=f"Image not found: {image_path}")

        # Determine content type
        suffix = image_path.suffix.lower()
        content_types = {
            ".png": "image/png",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".webp": "image/webp",
        }
        content_type = content_types.get(suffix, "image/png")

        # Pinterest v5 requires multipart upload for file-based pins
        # First, create a media upload
        try:
            # Register the media upload
            media_data = {
                "media_type": "image",
            }
            media_result = self._request("POST", "/media", json_data=media_data)
            media_id = media_result.get("media_id")
            upload_url = media_result.get("upload_url")

            if not upload_url:
                return PinResult(
                    success=False,
                    error="No upload URL returned from Pinterest",
                )

            # Upload the image
            with open(image_path, "rb") as f:
                upload_response = requests.put(
                    upload_url,
                    data=f.read(),
                    headers={"Content-Type": content_type},
                    timeout=60,
                )
                upload_response.raise_for_status()

            # Create the pin with the uploaded media
            pin_data = {
                "title": title[:100],
                "description": description[:500],
                "board_id": board_id,
                "link": link,
                "media_source": {
                    "source_type": "media_id",
                    "media_id": media_id,
                },
            }

            if alt_text:
                pin_data["alt_text"] = alt_text[:500]

            result = self._request("POST", "/pins", json_data=pin_data)
            pin_id = result.get("id", "")
            pin_url = f"https://www.pinterest.com/pin/{pin_id}/"

            logger.info(f"✅ Pin created (file upload): {title[:50]}... → {pin_url}")
            return PinResult(
                success=True,
                pin_id=pin_id,
                pin_url=pin_url,
                raw_response=result,
            )

        except Exception as e:
            error_msg = f"File upload failed: {e}"
            logger.error(f"❌ {error_msg}")
            return PinResult(success=False, error=error_msg)

    def get_pin(self, pin_id: str) -> dict[str, Any] | None:
        """Get details for a specific Pin.

        Args:
            pin_id: The Pin ID.

        Returns:
            Pin data dictionary, or None if not found.
        """
        try:
            return self._request("GET", f"/pins/{pin_id}")
        except Exception as e:
            logger.error(f"Failed to fetch pin {pin_id}: {e}")
            return None

    def get_pin_analytics(self, pin_id: str) -> dict[str, Any] | None:
        """Fetch analytics exposed for a Pin by the authorized API token."""
        try:
            return self._request(
                "GET",
                f"/pins/{pin_id}/analytics",
                params={"metric_types": "IMPRESSION,OUTBOUND_CLICK,SAVE"},
            )
        except Exception as e:
            logger.error(f"Failed to fetch analytics for pin {pin_id}: {e}")
            return None

    def delete_pin(self, pin_id: str) -> bool:
        """Delete a Pin.

        Args:
            pin_id: The Pin ID to delete.

        Returns:
            True if deleted successfully.
        """
        try:
            url = f"{self.base_url}/pins/{pin_id}"
            response = requests.delete(
                url,
                headers={"Authorization": f"Bearer {self.config.access_token}"},
                timeout=30,
            )
            response.raise_for_status()
            logger.info(f"Deleted pin: {pin_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to delete pin {pin_id}: {e}")
            return False
