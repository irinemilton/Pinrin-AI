"""
PinPilot Gumroad Client
Handles creating products on Gumroad via the Gumroad API.
"""
import logging
from pathlib import Path
from typing import Any
import requests
from .config import GumroadConfig

logger = logging.getLogger("pinpilot.gumroad")

class GumroadProduct:
    def __init__(self, data: dict[str, Any]):
        self.data = data
        self.id = data.get("id", "")
        self.name = data.get("name", "")
        self.short_url = data.get("short_url", "")
        self.price = data.get("price", 0)

    @property
    def url(self) -> str:
        return self.short_url or ""

class GumroadClient:
    BASE_URL = "https://api.gumroad.com/v2"

    def __init__(self, config: GumroadConfig):
        self.config = config

    def _request(self, method, endpoint, data=None, files=None, params=None):
        url = f"{self.BASE_URL}{endpoint}"
        if data is None:
            data = {}
        data["access_token"] = self.config.access_token
        response = requests.request(method=method, url=url, data=data, files=files, params=params, timeout=60)
        if not response.ok:
            response.raise_for_status()
        result = response.json()
        if not result.get("success", False):
            raise RuntimeError(f"Gumroad error: {result.get('message', 'Unknown')}")
        return result

    def create_product(self, name, description, price, product_file=None, preview_image=None, tags=None):
        data = {"name": name, "description": description, "price": price}
        if tags:
            data["tags"] = ",".join(tags)
        files = {}
        if product_file:
            p = Path(product_file)
            if p.exists():
                files["file"] = (p.name, open(p, "rb"), self._ct(p))
        if preview_image:
            p = Path(preview_image)
            if p.exists():
                files["preview"] = (p.name, open(p, "rb"), self._ct(p))
        try:
            result = self._request("POST", "/products", data=data, files=files or None)
            product = GumroadProduct(result.get("product", {}))
            logger.info(f"Product created: {product.name} -> {product.url}")
            return product
        finally:
            for _, ft in files.items():
                if hasattr(ft[1], "close"):
                    ft[1].close()

    def list_products(self):
        result = self._request("GET", "/products")
        return [GumroadProduct(p) for p in result.get("products", [])]

    def list_sales(self):
        """Return verified Gumroad sales exposed to the authorized token."""
        result = self._request("GET", "/sales", data={})
        return result.get("sales", [])

    @staticmethod
    def _ct(path):
        types = {".pdf": "application/pdf", ".zip": "application/zip", ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp"}
        return types.get(path.suffix.lower(), "application/octet-stream")
