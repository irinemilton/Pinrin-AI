"""MCP client for the Pinrin image-generation Gradio Space."""
from __future__ import annotations

import ast
import json
from pathlib import Path
from typing import Any

import requests


class ImageProviderError(RuntimeError):
    """Raised when the remote image provider cannot generate an image."""


class GradioMCPImageProvider:
    def __init__(self, endpoint: str, api_key: str = "", timeout: int = 360):
        self.endpoint = endpoint
        self.api_key = api_key
        self.timeout = timeout

    def _post(self, session: requests.Session, payload: dict[str, Any]) -> str:
        headers = {"Content-Type": "application/json", "Accept": "application/json, text/event-stream"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        response = session.post(
            self.endpoint,
            headers=headers,
            json=payload,
            timeout=self.timeout,
        )
        response.raise_for_status()
        messages = []
        for line in response.text.splitlines():
            if line.startswith("data: "):
                messages.append(json.loads(line[6:]))
        if not messages:
            raise ImageProviderError("Image provider returned no MCP response")
        result = messages[-1].get("result", {})
        if result.get("isError"):
            detail = result.get("content", [{}])[0].get("text", "generation failed")
            raise ImageProviderError(detail)
        text = result.get("content", [{}])[0].get("text", "")
        return text

    def generate(self, prompt: str, output_path: Path, aspect_ratio: str, steps: int) -> dict[str, Any]:
        session = requests.Session()
        self._post(session, {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-03-26", "capabilities": {}, "clientInfo": {"name": "pinrin", "version": "1.0"}}})
        headers = {"Content-Type": "application/json", "Accept": "application/json, text/event-stream"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        session.post(self.endpoint, headers=headers, json={"jsonrpc": "2.0", "method": "notifications/initialized"}, timeout=30)
        text = self._post(session, {"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"name": "qwen_image_2_1_uncensored_aio_loras_generate", "arguments": {"prompt": prompt, "mode": "Text to Image", "lora_adapter": "None (Base Uncensored)", "lora_strength": 1.0, "custom_repo": "", "custom_file": "", "aspect_ratio": aspect_ratio, "steps": steps, "seed": 42, "randomize_seed": True}}})
        try:
            files = ast.literal_eval(text.split("\n", 1)[0])
            image_url = next(item["url"] for item in files if isinstance(item, dict) and item.get("url"))
        except (SyntaxError, ValueError, KeyError, StopIteration) as exc:
            raise ImageProviderError("Image provider returned an invalid file result") from exc
        image = requests.get(image_url, timeout=self.timeout)
        image.raise_for_status()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(image.content)
        return {"path": str(output_path), "source_url": image_url, "provider": "huggingface_gradio_mcp"}
