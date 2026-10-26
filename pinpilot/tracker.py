"""
PinPilot Publish Tracker

Tracks which Pins have been published to prevent duplicates
and provides status reporting. Uses a local JSON file as
the persistence layer (no database needed).
"""

import json
import logging
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger("pinpilot.tracker")

# Default tracker file location
DEFAULT_TRACKER_PATH = Path("pinpilot_tracker.json")


@dataclass
class PublishRecord:
    """A single Pin publication record."""
    dedup_key: str
    product_name: str
    pin_id: str
    pin_url: str
    pin_title: str
    gumroad_url: str
    image_path: str
    board_id: str
    published_at: str = ""
    status: str = "published"
    user_id: str = "default"

    def __post_init__(self):
        if not self.published_at:
            self.published_at = datetime.now(timezone.utc).isoformat()


@dataclass
class TrackerData:
    """Full tracker state."""
    records: list[PublishRecord] = field(default_factory=list)
    total_published: int = 0
    last_run: str = ""
    version: str = "1.0"


class PublishTracker:
    """Tracks published Pins for deduplication and status reporting.

    Persists state to a local JSON file so it survives restarts.
    """

    def __init__(self, tracker_path: str | Path | None = None):
        self.path = Path(tracker_path) if tracker_path else DEFAULT_TRACKER_PATH
        self._data: TrackerData | None = None
        self._published_keys: set[str] = set()

    @property
    def data(self) -> TrackerData:
        """Lazy-load tracker data from file."""
        if self._data is None:
            self._load()
        return self._data  # type: ignore

    def _load(self) -> None:
        """Load tracker data from the JSON file."""
        if self.path.exists():
            try:
                raw = json.loads(self.path.read_text(encoding="utf-8"))
                records = [
                    PublishRecord(**r) for r in raw.get("records", [])
                ]
                self._data = TrackerData(
                    records=records,
                    total_published=raw.get("total_published", len(records)),
                    last_run=raw.get("last_run", ""),
                    version=raw.get("version", "1.0"),
                )
                self._published_keys = {r.dedup_key for r in records}
                logger.debug(
                    f"Loaded tracker: {len(records)} records from {self.path}"
                )
            except (json.JSONDecodeError, TypeError, KeyError) as e:
                logger.warning(f"Corrupt tracker file, starting fresh: {e}")
                self._data = TrackerData()
                self._published_keys = set()
        else:
            self._data = TrackerData()
            self._published_keys = set()

    def _save(self) -> None:
        """Persist tracker data to the JSON file."""
        data = self.data
        output = {
            "version": data.version,
            "total_published": data.total_published,
            "last_run": data.last_run,
            "records": [asdict(r) for r in data.records],
        }

        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps(output, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        logger.debug(f"Saved tracker: {len(data.records)} records to {self.path}")

    def is_published(self, dedup_key: str) -> bool:
        """Check if a Pin has already been published.

        Args:
            dedup_key: The deduplication key (product|image|title).

        Returns:
            True if this exact Pin was already published.
        """
        return dedup_key in self._published_keys

    def record(self, pub_record: PublishRecord) -> None:
        """Record a new Pin publication.

        Args:
            pub_record: The publication record to save.
        """
        self.data.records.append(pub_record)
        self.data.total_published += 1
        self.data.last_run = datetime.now(timezone.utc).isoformat()
        self._published_keys.add(pub_record.dedup_key)
        self._save()

        logger.info(
            f"Tracked: {pub_record.pin_title[:40]}... "
            f"(total: {self.data.total_published})"
        )

    def get_records_for_product(self, product_name: str) -> list[PublishRecord]:
        """Get all publication records for a specific product.

        Args:
            product_name: The product folder name.

        Returns:
            List of matching PublishRecord objects.
        """
        return [
            r for r in self.data.records
            if r.product_name == product_name
        ]

    def get_summary(self) -> dict[str, Any]:
        """Get a summary of all publishing activity.

        Returns:
            Dictionary with counts and breakdowns by product.
        """
        data = self.data
        by_product: dict[str, int] = {}
        by_status: dict[str, int] = {}

        for record in data.records:
            by_product[record.product_name] = (
                by_product.get(record.product_name, 0) + 1
            )
            by_status[record.status] = (
                by_status.get(record.status, 0) + 1
            )

        return {
            "total_published": data.total_published,
            "last_run": data.last_run,
            "products": by_product,
            "statuses": by_status,
            "record_count": len(data.records),
        }

    def clear(self) -> None:
        """Clear all tracking data. Use with caution!"""
        self._data = TrackerData()
        self._published_keys = set()
        self._save()
        logger.warning("Tracker data cleared!")

    def export_csv(self, output_path: str | Path) -> Path:
        """Export all records to a CSV file.

        Args:
            output_path: Where to save the CSV.

        Returns:
            Path to the created CSV file.
        """
        import csv

        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        fields = [
            "published_at", "product_name", "pin_title",
            "pin_id", "pin_url", "gumroad_url",
            "image_path", "board_id", "status",
        ]

        with open(output_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
            writer.writeheader()
            for record in self.data.records:
                writer.writerow(asdict(record))

        logger.info(f"Exported {len(self.data.records)} records to {output_path}")
        return output_path
