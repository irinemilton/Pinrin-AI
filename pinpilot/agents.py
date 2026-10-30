"""Specialized agents used by the autonomous campaign orchestrator.

Agents return observable summaries and structured artifacts. They never expose
hidden model reasoning and never turn missing external data into facts.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Callable

import requests

from .config import Config
from .gumroad_client import GumroadClient
from .pinterest_client import PinterestClient
from .tracker import PublishTracker

logger = logging.getLogger("pinpilot.agents")
EventWriter = Callable[[str, str, str, dict[str, Any] | None], None]


class AgentBlocked(RuntimeError):
    """Raised when an agent lacks a required configured capability."""


class HuggingFaceAdapter:
    """Server-only adapter for Hugging Face's OpenAI-compatible router."""

    def __init__(self, config: Config):
        self.config = config
        self.api_key = config.agent.huggingface_token

    @property
    def configured(self) -> bool:
        return bool(self.api_key)

    def health(self) -> dict[str, Any]:
        if not self.configured:
            return {"provider": "huggingface", "status": "not_configured", "model": self.config.agent.model}
        try:
            response = requests.post(
                "https://router.huggingface.co/v1/chat/completions",
                headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
                json={"model": self.config.agent.model, "messages": [{"role": "user", "content": "Reply OK"}], "max_tokens": 4},
                timeout=30,
            )
            return {"provider": "huggingface", "status": "ready" if response.ok else "unavailable", "http_status": response.status_code, "model": self.config.agent.model}
        except requests.RequestException as exc:
            return {"provider": "huggingface", "status": "unavailable", "model": self.config.agent.model, "error": str(exc)}

    def generate_json(self, instruction: str, schema_name: str) -> dict[str, Any]:
        if not self.configured:
            raise AgentBlocked("HUGGINGFACE_API_TOKEN is not configured")
        response = requests.post(
            "https://router.huggingface.co/v1/chat/completions",
            headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
            json={
                "model": self.config.agent.model,
                "messages": [{"role": "system", "content": "Return only valid JSON. Do not reveal hidden reasoning."}, {"role": "user", "content": instruction}],
                "max_tokens": 1800,
                "temperature": 0.2,
            },
            timeout=90,
        )
        if response.status_code in (401, 403):
            raise AgentBlocked(f"Hugging Face authentication failed ({response.status_code})")
        if response.status_code == 402:
            raise AgentBlocked("Hugging Face inference requires provider credits or billing")
        response.raise_for_status()
        payload = response.json()
        text = payload.get("choices", [{}])[0].get("message", {}).get("content", "")
        try:
            return json.loads(text)
        except (TypeError, json.JSONDecodeError) as exc:
            raise AgentBlocked("Hugging Face returned no valid structured JSON") from exc


class AgentSuite:
    """Five bounded specialists with explicit inputs and outputs."""

    def __init__(self, config: Config, tracker: PublishTracker, emit: EventWriter):
        self.config = config
        self.tracker = tracker
        self.emit = emit
        self.llm = HuggingFaceAdapter(config)

    def run_trend_scout(self, goal: str) -> dict[str, Any]:
        self.emit("trend_scout", "started", "Collecting permitted trend observations.", None)
        observations: list[dict[str, Any]] = []
        if self.config.agent.trends_json:
            try:
                parsed = json.loads(self.config.agent.trends_json)
                observations = parsed if isinstance(parsed, list) else parsed.get("observations", [])
            except json.JSONDecodeError as exc:
                raise AgentBlocked(f"PINTEREST_TRENDS_JSON is invalid: {exc}") from exc
        elif self.config.pinterest.access_token:
            trends_url = self.config.agent.trends_url or f"{self.config.pinterest.base_url}/trends/keywords/{self.config.agent.trends_region}/top/{self.config.agent.trends_type}"
            response = requests.get(trends_url, headers={"Authorization": f"Bearer {self.config.pinterest.access_token}"}, params={"limit": self.config.agent.trends_limit}, timeout=30)
            if response.status_code in (401, 403):
                raise AgentBlocked(f"Pinterest Trends authentication failed ({response.status_code})")
            response.raise_for_status()
            payload = response.json()
            raw_trends = payload if isinstance(payload, list) else payload.get("items", payload.get("trends", []))
            observations = [{"keyword": item.get("keyword", ""), "growth_wow": item.get("pct_growth_wow"), "growth_mom": item.get("pct_growth_mom"), "growth_yoy": item.get("pct_growth_yoy"), "time_series": item.get("time_series", {}), "region": self.config.agent.trends_region, "trend_type": self.config.agent.trends_type, "url": trends_url} for item in raw_trends]
        if not observations:
            self.emit("trend_scout", "blocked", "No permitted Pinterest Trends source is configured.", {"evidence": []})
            return {"status": "unavailable", "observations": [], "evidence": []}
        output = {"status": "complete", "goal": goal, "observations": observations, "evidence": [o.get("url") for o in observations if o.get("url")]}
        self.emit("trend_scout", "completed", "Trend observations collected.", output)
        return output

    def run_opportunity_analyst(self, goal: str, trends: dict[str, Any]) -> dict[str, Any]:
        self.emit("opportunity_analyst", "started", "Scoring ideas against explicit criteria.", None)
        prompt = f"""You are the Opportunity Analyst. Return JSON only with an ideas array.\nGoal: {goal}\nPermitted trend observations: {json.dumps(trends)}\nEach idea must have name, audience, problem, scores (relevance, demand, differentiation, effort, commercial_risk), reasons, and uncertainty. Scores are prioritization aids, never sales predictions. Do not claim evidence that is absent."""
        if self.llm.configured:
            result = self.llm.generate_json(prompt, "opportunity_analysis")
        else:
            result = {"ideas": [{"name": "Configured goal hypothesis", "audience": "From campaign goal", "problem": goal, "scores": {}, "reasons": ["Derived from configured goal only"], "uncertainty": ["No trend source or model is available"]}]}
        result["status"] = "complete" if trends.get("status") == "complete" or self.llm.configured else "hypothesis"
        self.emit("opportunity_analyst", "completed", "Opportunity shortlist prepared.", result)
        return result

    def run_product_builder(self, goal: str, opportunity: dict[str, Any]) -> dict[str, Any]:
        self.emit("product_builder", "started", "Planning product structure and dependencies.", None)
        product_path = Path(self.config.agent.product_file) if self.config.agent.product_file else None
        if product_path and product_path.exists():
            result = {"status": "source_supplied", "file": str(product_path), "outline": [], "message": "Using the configured product artifact."}
        elif not self.llm.configured:
            raise AgentBlocked("Product generation requires a valid HUGGINGFACE_API_TOKEN or AGENT_PRODUCT_FILE")
        else:
            result = self.llm.generate_json(f"You are the Product Builder. Return editable product metadata and an outline. Goal: {goal}. Selected opportunity: {json.dumps(opportunity)}. Do not claim a file was rendered.", "product_blueprint")
            result["status"] = "planned"
        self.emit("product_builder", "completed", "Product plan is ready for validation.", result)
        return result

    def run_marketing_assistant(self, goal: str, product: dict[str, Any]) -> dict[str, Any]:
        self.emit("marketing_assistant", "started", "Preparing an approval-ready marketing queue.", None)
        if not self.llm.configured:
            raise AgentBlocked("Marketing copy requires a valid HUGGINGFACE_API_TOKEN")
        result = self.llm.generate_json(f"You are the Marketing Assistant. Return a weekly queue with Pin headline variations, keyword-aware descriptions, visual briefs, and campaign links. Goal: {goal}. Product plan: {json.dumps(product)}. Do not invent product features.", "marketing_queue")
        result["status"] = "draft"
        self.emit("marketing_assistant", "completed", "Marketing queue is awaiting approval.", result)
        return result

    def run_performance_analyst(self) -> dict[str, Any]:
        self.emit("performance_analyst", "started", "Reading available publication records and metrics.", None)
        summary = self.tracker.get_summary()
        metrics: list[dict[str, Any]] = []
        for record in self.tracker.data.records:
            if record.pin_id and self.config.pinterest.is_configured:
                analytics = PinterestClient(self.config.pinterest).get_pin_analytics(record.pin_id)
                if analytics is not None:
                    metrics.append({"source": "pinterest", "pin_id": record.pin_id, "data": analytics})
        sales: list[dict[str, Any]] = []
        if self.config.gumroad.access_token:
            try:
                sales = GumroadClient(self.config.gumroad).list_sales()
            except Exception as exc:
                logger.warning("Gumroad analytics unavailable: %s", exc)
        recommendations = []
        if metrics:
            recommendations.append("Compare Pin impressions and outbound clicks before changing the product offer.")
        if sales:
            recommendations.append("Compare attributed sales with outbound clicks before increasing promotion.")
        result = {"status": "complete" if metrics or sales else "partial", "observed": summary, "metrics": metrics, "sales": sales, "recommendations": recommendations, "message": "Metrics are limited to values returned by authorized platform adapters."}
        self.emit("performance_analyst", "completed", "Observed records summarized; platform metrics unavailable.", result)
        return result
