"""
PinPilot Configuration Module

Loads environment variables and provides typed configuration access.
"""

import os
from dataclasses import dataclass, field
from pathlib import Path
from dotenv import load_dotenv


@dataclass
class DropboxConfig:
    """Dropbox API configuration."""
    app_key: str = ""
    app_secret: str = ""
    access_token: str = ""
    products_path: str = "/PinPilot/products"
    published_path: str = "/PinPilot/published"

    @property
    def is_configured(self) -> bool:
        return bool(self.access_token)


@dataclass
class PinterestConfig:
    """Pinterest API configuration."""
    access_token: str = ""
    board_id: str = ""
    sandbox: bool = True

    @property
    def base_url(self) -> str:
        if self.sandbox:
            return "https://api-sandbox.pinterest.com/v5"
        return "https://api.pinterest.com/v5"

    @property
    def is_configured(self) -> bool:
        return bool(self.access_token and self.board_id)


@dataclass
class GumroadConfig:
    """Gumroad configuration."""
    store_url: str = ""
    access_token: str = ""

    @property
    def is_configured(self) -> bool:
        return bool(self.store_url)


@dataclass
class PublishingConfig:
    """Publishing behavior configuration."""
    max_pins_per_run: int = 10
    pin_publish_delay: int = 30  # seconds
    schedule_interval_hours: int = 6


@dataclass
class LogConfig:
    """Logging configuration."""
    level: str = "INFO"
    log_file: str = "pinpilot.log"


@dataclass
class AgentConfig:
    """Configuration for the autonomous campaign workflow."""
    campaign_goal: str = ""
    product_file: str = ""
    pin_images: list[str] = field(default_factory=list)
    board_name: str = ""
    product_title: str = ""
    price: int = 0
    model: str = "gpt-4.1-mini"
    huggingface_token: str = ""
    trends_json: str = ""
    trends_url: str = ""
    schedule_interval_hours: int = 24
    max_retries: int = 2


@dataclass
class Config:
    """Master configuration for PinPilot."""
    dropbox: DropboxConfig = field(default_factory=DropboxConfig)
    pinterest: PinterestConfig = field(default_factory=PinterestConfig)
    gumroad: GumroadConfig = field(default_factory=GumroadConfig)
    publishing: PublishingConfig = field(default_factory=PublishingConfig)
    logging: LogConfig = field(default_factory=LogConfig)
    agent: AgentConfig = field(default_factory=AgentConfig)

    @classmethod
    def from_env(cls, env_path: str | Path | None = None) -> "Config":
        """Load configuration from environment variables.

        Args:
            env_path: Optional path to a .env file. If None, looks for .env
                      in the current directory and parent directories.

        Returns:
            A fully populated Config instance.
        """
        if env_path:
            load_dotenv(env_path)
        else:
            load_dotenv()

        huggingface_token = os.getenv("HUGGINGFACE_API_TOKEN", os.getenv("HF_TOKEN", ""))
        if not huggingface_token:
            dotenv_path = Path(env_path) if env_path else Path(".env")
            if dotenv_path.exists():
                for line in dotenv_path.read_text(encoding="utf-8").splitlines():
                    candidate = line.strip()
                    if candidate.startswith("hf_"):
                        huggingface_token = candidate
        return cls(
            dropbox=DropboxConfig(
                app_key=os.getenv("DROPBOX_APP_KEY", ""),
                app_secret=os.getenv("DROPBOX_APP_SECRET", ""),
                access_token=os.getenv("DROPBOX_ACCESS_TOKEN", ""),
                products_path=os.getenv("DROPBOX_PRODUCTS_PATH", "/PinPilot/products"),
                published_path=os.getenv("DROPBOX_PUBLISHED_PATH", "/PinPilot/published"),
            ),
            pinterest=PinterestConfig(
                access_token=os.getenv("PINTEREST_ACCESS_TOKEN", ""),
                board_id=os.getenv("PINTEREST_BOARD_ID", ""),
                sandbox=os.getenv("PINTEREST_SANDBOX", "true").lower() == "true",
            ),
            gumroad=GumroadConfig(
                store_url=os.getenv("GUMROAD_STORE_URL", ""),
                access_token=os.getenv("GUMROAD_ACCESS_TOKEN", ""),
            ),
            publishing=PublishingConfig(
                max_pins_per_run=int(os.getenv("MAX_PINS_PER_RUN", "10")),
                pin_publish_delay=int(os.getenv("PIN_PUBLISH_DELAY", "30")),
                schedule_interval_hours=int(os.getenv("SCHEDULE_INTERVAL_HOURS", "6")),
            ),
            logging=LogConfig(
                level=os.getenv("LOG_LEVEL", "INFO"),
                log_file=os.getenv("LOG_FILE", "pinpilot.log"),
            ),
            agent=AgentConfig(
                campaign_goal=os.getenv("AGENT_CAMPAIGN_GOAL", ""),
                product_file=os.getenv("AGENT_PRODUCT_FILE", ""),
                pin_images=[p.strip() for p in os.getenv("AGENT_PIN_IMAGES", "").split(",") if p.strip()],
                board_name=os.getenv("AGENT_BOARD_NAME", ""),
                product_title=os.getenv("AGENT_PRODUCT_TITLE", ""),
                price=int(os.getenv("AGENT_PRICE", "0")),
                model=os.getenv("HUGGINGFACE_TEXT_MODEL", "Qwen/Qwen2.5-72B-Instruct"),
                huggingface_token=huggingface_token,
                trends_json=os.getenv("PINTEREST_TRENDS_JSON", ""),
                trends_url=os.getenv("PINTEREST_TRENDS_URL", ""),
                schedule_interval_hours=int(os.getenv("AGENT_SCHEDULE_INTERVAL_HOURS", "24")),
                max_retries=int(os.getenv("AGENT_MAX_RETRIES", "2")),
            ),
        )

    def validate(self) -> list[str]:
        """Check configuration and return a list of warnings/errors.

        Returns:
            List of warning messages. Empty list means all is good.
        """
        issues = []

        if not self.dropbox.is_configured:
            issues.append("⚠️  Dropbox access token not set — cannot fetch product files")

        if not self.pinterest.is_configured:
            if not self.pinterest.access_token:
                issues.append("⚠️  Pinterest access token not set — cannot publish Pins")
            if not self.pinterest.board_id:
                issues.append("⚠️  Pinterest board ID not set — Pins need a target board")

        if not self.gumroad.is_configured:
            issues.append("⚠️  Gumroad store URL not set — Pins won't link to a product")

        if self.pinterest.sandbox:
            issues.append("ℹ️  Pinterest sandbox mode is ON — Pins won't be publicly visible")

        if not self.agent.campaign_goal:
            issues.append("⚠️  AGENT_CAMPAIGN_GOAL not set — autonomous runs need a configured goal")
        if not self.agent.huggingface_token:
            issues.append("⚠️  HUGGINGFACE_API_TOKEN not set — model-backed agents cannot run")
        if not self.agent.product_file:
            issues.append("⚠️  AGENT_PRODUCT_FILE not set — publishing needs a product artifact")
        if not self.agent.pin_images:
            issues.append("⚠️  AGENT_PIN_IMAGES not set — Pinterest publishing needs creatives")
        if self.agent.price <= 0:
            issues.append("⚠️  AGENT_PRICE must be greater than zero for Gumroad publication")

        return issues
