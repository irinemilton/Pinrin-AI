"""
PinPilot Publisher Engine

Orchestrates the full pipeline: fetch products from Dropbox,
generate Pin metadata, publish to Pinterest, track results,
and handle deduplication.
"""

import json
import logging
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .config import Config
from .dropbox_client import DropboxClient, ProductFolder
from .pinterest_client import PinterestClient, PinResult
from .tracker import PublishTracker, PublishRecord

logger = logging.getLogger("pinpilot.publisher")


class Publisher:
    """Main publishing engine that coordinates the full pipeline."""

    def __init__(self, config: Config, tracker: PublishTracker | None = None):
        self.config = config
        self.dropbox = DropboxClient(config.dropbox)
        self.pinterest = PinterestClient(config.pinterest)
        self.tracker = tracker or PublishTracker()

    def validate_setup(self) -> tuple[bool, list[str]]:
        """Validate all API connections and configuration.

        Returns:
            Tuple of (all_ok, list_of_messages).
        """
        messages = self.config.validate()
        all_ok = True

        # Test Dropbox
        if self.config.dropbox.is_configured:
            try:
                folders = self.dropbox.list_product_folders()
                messages.append(f"✅ Dropbox: {len(folders)} product folder(s) found")
            except Exception as e:
                messages.append(f"❌ Dropbox connection failed: {e}")
                all_ok = False
        else:
            all_ok = False

        # Test Pinterest
        if self.config.pinterest.is_configured:
            user = self.pinterest.verify_connection()
            if user:
                messages.append(
                    f"✅ Pinterest: connected as @{user.get('username', 'unknown')}"
                )
            else:
                messages.append("❌ Pinterest connection failed")
                all_ok = False
        else:
            all_ok = False

        return all_ok, messages

    def _generate_pin_variations(
        self, product: ProductFolder
    ) -> list[dict[str, str]]:
        """Generate Pin title/description variations for a product.

        Uses the variations defined in product.json, or falls back to
        generating variations from the base title/description.

        Args:
            product: The product to generate variations for.

        Returns:
            List of dicts with 'pin_title' and 'pin_description' keys.
        """
        # Use custom variations if provided
        if product.variations:
            return product.variations

        # Generate default variations from base metadata
        base_title = product.title
        base_desc = product.description
        tags_str = " ".join(f"#{tag.replace(' ', '')}" for tag in product.tags[:5])

        variations = [
            {
                "pin_title": base_title,
                "pin_description": f"{base_desc} {tags_str}".strip(),
            },
        ]

        # Add a second variation with a different angle
        if product.price:
            variations.append({
                "pin_title": f"Get {base_title} — {product.price}",
                "pin_description": (
                    f"Instant digital download. {base_desc[:200]} {tags_str}"
                ).strip(),
            })

        return variations

    def _resolve_board_id(self, product: ProductFolder) -> str:
        """Determine the board ID for a product.

        Uses the board name from product metadata, or falls back to the
        default board ID from config.

        Args:
            product: The product to find a board for.

        Returns:
            Board ID string.
        """
        if product.board:
            # Look up or create the board by name
            return self.pinterest.get_or_create_board(
                product.board,
                description=f"Products: {product.board}",
            )
        return self.config.pinterest.board_id

    def publish_product(
        self,
        product: ProductFolder,
        dry_run: bool = False,
        max_pins: int | None = None,
    ) -> list[PinResult]:
        """Publish Pins for a single product.

        Creates one Pin per image × variation combination, up to max_pins.

        Args:
            product: The product to publish.
            dry_run: If True, log what would be published without actually doing it.
            max_pins: Maximum number of Pins to create. Uses config default if None.

        Returns:
            List of PinResult objects.
        """
        results: list[PinResult] = []
        max_pins = max_pins or self.config.publishing.max_pins_per_run
        variations = self._generate_pin_variations(product)

        if not product.gumroad_url:
            logger.warning(
                f"Skipping {product.name}: no gumroad_url in product.json"
            )
            return results

        if not product.image_paths:
            logger.warning(f"Skipping {product.name}: no images found")
            return results

        # Resolve board
        try:
            board_id = self._resolve_board_id(product)
        except Exception as e:
            logger.error(f"Failed to resolve board for {product.name}: {e}")
            return results

        pin_count = 0
        for image_path in product.image_paths:
            for variation in variations:
                if pin_count >= max_pins:
                    logger.info(
                        f"Reached max pins ({max_pins}) for {product.name}"
                    )
                    return results

                title = variation["pin_title"]
                description = variation["pin_description"]

                # Check for duplicates
                dedup_key = f"{product.name}|{Path(image_path).name}|{title}"
                if self.tracker.is_published(dedup_key):
                    logger.debug(f"Skipping duplicate: {dedup_key}")
                    continue

                if dry_run:
                    logger.info(
                        f"[DRY RUN] Would publish Pin:\n"
                        f"  Title:  {title}\n"
                        f"  Desc:   {description[:80]}...\n"
                        f"  Image:  {image_path}\n"
                        f"  Link:   {product.gumroad_url}\n"
                        f"  Board:  {board_id}"
                    )
                    results.append(
                        PinResult(success=True, pin_id="dry-run", pin_url="dry-run")
                    )
                    pin_count += 1
                    continue

                # Get a temporary URL for the image from Dropbox
                image_url = self.dropbox.get_temporary_link(image_path)
                if not image_url:
                    logger.error(f"Failed to get image URL for: {image_path}")
                    results.append(
                        PinResult(
                            success=False,
                            error=f"No temp link for {image_path}",
                        )
                    )
                    continue

                # Publish the Pin
                result = self.pinterest.create_pin_from_url(
                    title=title,
                    description=description,
                    image_url=image_url,
                    link=product.gumroad_url,
                    board_id=board_id,
                    alt_text=f"{product.title} — digital download",
                )

                results.append(result)

                if result.success:
                    # Record in tracker
                    record = PublishRecord(
                        dedup_key=dedup_key,
                        product_name=product.name,
                        pin_id=result.pin_id or "",
                        pin_url=result.pin_url or "",
                        pin_title=title,
                        gumroad_url=product.gumroad_url,
                        image_path=image_path,
                        board_id=board_id,
                        published_at=datetime.now(timezone.utc).isoformat(),
                    )
                    self.tracker.record(record)
                    pin_count += 1

                    # Delay between pins to avoid rate limits
                    if pin_count < max_pins:
                        delay = self.config.publishing.pin_publish_delay
                        logger.debug(f"Waiting {delay}s before next Pin...")
                        time.sleep(delay)

        return results

    def publish_all(
        self,
        dry_run: bool = False,
        max_pins_total: int | None = None,
    ) -> dict[str, list[PinResult]]:
        """Publish Pins for all unpublished products.

        Args:
            dry_run: If True, preview without publishing.
            max_pins_total: Maximum total Pins across all products.

        Returns:
            Dictionary mapping product name → list of PinResults.
        """
        max_total = max_pins_total or self.config.publishing.max_pins_per_run
        all_results: dict[str, list[PinResult]] = {}
        total_published = 0

        products = self.dropbox.get_all_products()
        if not products:
            logger.warning("No products found in Dropbox. Nothing to publish.")
            return all_results

        logger.info(f"Found {len(products)} product(s) to process")

        for product in products:
            remaining = max_total - total_published
            if remaining <= 0:
                logger.info("Reached total pin limit. Stopping.")
                break

            logger.info(f"\n{'='*60}")
            logger.info(f"Processing: {product.name}")
            logger.info(f"  Title:  {product.title}")
            logger.info(f"  Images: {len(product.image_paths)}")
            logger.info(f"  Vars:   {len(product.variations) or 'auto-generated'}")
            logger.info(f"{'='*60}")

            results = self.publish_product(
                product, dry_run=dry_run, max_pins=remaining
            )
            all_results[product.name] = results

            successes = sum(1 for r in results if r.success)
            failures = sum(1 for r in results if not r.success)
            total_published += successes

            logger.info(
                f"  Results: {successes} published, {failures} failed"
            )

        # Summary
        total_success = sum(
            sum(1 for r in results if r.success)
            for results in all_results.values()
        )
        total_fail = sum(
            sum(1 for r in results if not r.success)
            for results in all_results.values()
        )

        logger.info(f"\n{'='*60}")
        logger.info(f"PUBLISHING COMPLETE")
        logger.info(f"  Products processed: {len(all_results)}")
        logger.info(f"  Pins published:     {total_success}")
        logger.info(f"  Pins failed:        {total_fail}")
        logger.info(f"{'='*60}")

        return all_results
