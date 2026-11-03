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
from .image_provider import GradioMCPImageProvider, ImageProviderError
from .pinterest_client import PinterestClient
from .tracker import PublishTracker

logger = logging.getLogger("pinpilot.agents")
EventWriter = Callable[[str, str, str, dict[str, Any] | None], None]


class AgentBlocked(RuntimeError):
    """Raised when an agent lacks a required configured capability."""


class HuggingFaceAdapter:
    """Server-only adapter for configured OpenAI-compatible reasoning providers."""

    def __init__(self, config: Config):
        self.config = config
        self.provider = config.agent.provider
        provider_values = {
            "openrouter": (config.agent.openrouter_token, config.agent.openrouter_base_url),
            "novita": (config.agent.novita_token, config.agent.novita_base_url),
            "huggingface": (config.agent.huggingface_token, "https://router.huggingface.co/v1"),
        }
        self.api_key, self.base_url = provider_values.get(self.provider, provider_values["huggingface"])

    @property
    def configured(self) -> bool:
        return bool(self.api_key)

    def model_for(self, role: str = "") -> str:
        role_model = getattr(self.config.agent, f"{role}_model", "") if role else ""
        provider_model = {
            "openrouter": self.config.agent.openrouter_model,
            "novita": self.config.agent.novita_model,
            "huggingface": self.config.agent.model,
        }.get(self.provider, self.config.agent.model)
        return role_model or provider_model

    def _label(self) -> str:
        return self.provider

    def _fallback_configured(self) -> bool:
        return self.provider in {"novita", "openrouter"} and bool(self.config.agent.huggingface_token)

    def _fallback_generate_json(self, instruction: str) -> dict[str, Any]:
        response = requests.post(
            "https://router.huggingface.co/v1/chat/completions",
            headers={"Authorization": f"Bearer {self.config.agent.huggingface_token}", "Content-Type": "application/json"},
            json={"model": self.config.agent.model, "messages": [{"role": "user", "content": instruction}], "max_tokens": 1800, "temperature": 0.2},
            timeout=90,
        )
        if response.status_code in (401, 403):
            raise AgentBlocked(f"Hugging Face fallback authentication failed ({response.status_code})")
        response.raise_for_status()
        text = self._response_text(response.json())
        try:
            return self._parse_json(text)
        except (TypeError, json.JSONDecodeError) as exc:
            raise AgentBlocked("Hugging Face fallback returned no valid structured JSON") from exc

    @staticmethod
    def _response_text(payload: dict[str, Any]) -> Any:
        content = payload.get("choices", [{}])[0].get("message", {}).get("content", "")
        if isinstance(content, list):
            return "".join(str(part.get("text", "")) if isinstance(part, dict) else str(part) for part in content)
        return content

    @staticmethod
    def _parse_json(text: Any) -> dict[str, Any]:
        if isinstance(text, dict):
            return text
        if not isinstance(text, str):
            raise TypeError("model content was not text")
        cleaned = text.strip()
        if cleaned.startswith("```"):
            lines = cleaned.splitlines()
            if lines and lines[0].strip().lower().startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            cleaned = "\n".join(lines).strip()
        try:
            parsed = json.loads(cleaned)
        except json.JSONDecodeError:
            start = cleaned.find("{")
            end = cleaned.rfind("}")
            if start < 0 or end <= start:
                raise
            parsed = json.loads(cleaned[start:end + 1])
        if not isinstance(parsed, dict):
            raise TypeError("model JSON must be an object")
        return parsed

    def health(self) -> dict[str, Any]:
        if not self.configured:
            return {"provider": self.provider, "status": "not_configured", "model": self.model_for()}
        try:
            response = requests.post(
                f"{self.base_url}/chat/completions",
                headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
                json={"model": self.model_for(), "messages": [{"role": "user", "content": "Reply OK"}], "max_tokens": 4},
                timeout=30,
            )
            details = response.json() if response.headers.get("content-type", "").startswith("application/json") else {}
            return {"provider": self.provider, "status": "ready" if response.ok else "unavailable", "http_status": response.status_code, "model": self.model_for(), "error": details.get("message") if details else None}
        except requests.RequestException as exc:
            return {"provider": self.provider, "status": "unavailable", "model": self.model_for(), "error": str(exc)}

    def generate_json(self, instruction: str, schema_name: str, role: str = "") -> dict[str, Any]:
        if not self.configured:
            raise AgentBlocked(f"{self.provider} API credentials are not configured")
        response = requests.post(
            f"{self.base_url}/chat/completions",
            headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
            json={
                "model": self.model_for(role),
                "messages": [{"role": "system", "content": "Return only valid JSON. Do not reveal hidden reasoning."}, {"role": "user", "content": instruction}],
                "max_tokens": 1800,
                "temperature": 0.2,
            },
            timeout=90,
        )
        if response.status_code == 403 and "NOT_ENOUGH_BALANCE" in response.text:
            if self._fallback_configured():
                logger.warning("%s text generation failed; trying Hugging Face fallback.", self.provider)
                return self._fallback_generate_json(instruction)
            raise AgentBlocked(f"{self._label()} account has insufficient balance")
        if response.status_code in (401, 403):
            if self._fallback_configured():
                logger.warning("%s authentication failed; trying Hugging Face fallback.", self.provider)
                return self._fallback_generate_json(instruction)
            raise AgentBlocked(f"{self._label()} authentication failed ({response.status_code})")
        if response.status_code == 402:
            if self._fallback_configured():
                logger.warning("%s inference requires billing; trying Hugging Face fallback.", self.provider)
                return self._fallback_generate_json(instruction)
            raise AgentBlocked(f"{self._label()} inference requires provider credits or billing")
        response.raise_for_status()
        payload = response.json()
        text = self._response_text(payload)
        try:
            return self._parse_json(text)
        except (TypeError, json.JSONDecodeError) as exc:
            raise AgentBlocked(f"{self._label()} returned no valid structured JSON") from exc


class AgentSuite:
    """Five bounded specialists with explicit inputs and outputs."""

    def __init__(self, config: Config, tracker: PublishTracker, emit: EventWriter):
        self.config = config
        self.tracker = tracker
        self.emit = emit
        self.llm = HuggingFaceAdapter(config)

    @staticmethod
    def _compact(value: Any, limit: int = 3200) -> str:
        text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=True)
        if len(text) <= limit:
            return text
        return text[:limit] + "\n[Additional context omitted to stay within the provider prompt limit.]"

    def _trend_context(self, trends: dict[str, Any]) -> str:
        observations = trends.get("observations", []) if isinstance(trends, dict) else []
        return self._compact(observations[:8], 1200)

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
        prompt = f"""You are the Opportunity Analyst for an autonomous digital-product studio.
Return JSON only with an ideas array. Produce 3 genuinely different opportunities, each with a distinct audience, problem, product angle, and creative theme.
Goal: {self._compact(goal, 800)}
Trend evidence available right now: {self._trend_context(trends)}
Creative direction: {self._compact(self.config.agent.creative_direction, 400)}
Additional role instructions: {self._compact(self.config.agent.opportunity_instructions, 500)}
For each idea include: name, audience, problem, promise, theme, differentiation, visual_concept, trend_evidence, scores (relevance, demand, differentiation, effort, commercial_risk), reasons, and uncertainty.
Use trend keywords as directional signals, not proof of demand. Prefer surprising combinations and underserved use cases. Never copy a trend title into a product name without adding a differentiated angle. Scores are prioritization aids, never sales predictions. Do not claim evidence that is absent."""
        if self.llm.configured:
            result = self.llm.generate_json(prompt, "opportunity_analysis", "opportunity")
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
            raise AgentBlocked("Product generation requires configured model credentials or AGENT_PRODUCT_FILE")
        else:
            result = self.llm.generate_json(f"""You are the Product Builder.
Return JSON only with editable product metadata and an outline.
Goal: {self._compact(goal, 800)}
Selected opportunity: {self._compact(opportunity, 1500)}
Creative direction: {self._compact(self.config.agent.creative_direction, 400)}
Additional role instructions: {self._compact(self.config.agent.product_instructions, 500)}
Design a product that is useful without relying on invented statistics. Include title, promise, audience, theme, differentiator, outline, exercises, deliverables, validation_questions, and price. Set price to a numeric US-dollar amount from 1.00 through 3.00 based on the product's scope and value. Do not use a currency symbol, and do not claim a file was rendered.""", "product_blueprint", "product")
            result["status"] = "planned"
        self.emit("product_builder", "completed", "Product plan is ready for validation.", result)
        return result

    def run_marketing_assistant(self, goal: str, product: dict[str, Any], trends: dict[str, Any] | None = None) -> dict[str, Any]:
        self.emit("marketing_assistant", "started", "Preparing an approval-ready marketing queue.", None)
        if not self.llm.configured:
            raise AgentBlocked("Marketing copy requires configured model credentials")
        result = self.llm.generate_json(f"""You are the Marketing Assistant and creative director.
Return JSON only with a queue array containing 4 distinct Pinterest concepts.
Goal: {self._compact(goal, 800)}
Product plan: {self._compact(product, 1500)}
Current trend evidence: {self._trend_context(trends or {})}
Creative direction: {self._compact(self.config.agent.creative_direction, 400)}
Additional role instructions: {self._compact(self.config.agent.marketing_instructions, 500)}
Each concept must include: theme, hook, headline, description, keywords, visual_brief, audience_angle, cta, trend_used, and uncertainty. Make the four concepts visually and emotionally different: do not repeat the same palette, composition, promise, or hook. Use keywords naturally, never stuff them. Do not invent product features, testimonials, rankings, or guaranteed outcomes.""", "marketing_queue", "marketing")
        result["status"] = "draft"
        self.emit("marketing_assistant", "completed", "Marketing queue is awaiting approval.", result)
        return result

    def run_image_generation(self, goal: str, product: dict[str, Any], marketing: dict[str, Any], output_dir: Path, trends: dict[str, Any] | None = None, concept_index: int = 0) -> dict[str, Any]:
        self.emit("image_generator", "started", "Generating an approval-ready Pinterest creative.", None)
        visual_brief = ""
        queue = marketing.get("queue", []) if isinstance(marketing, dict) else []
        concept = queue[concept_index] if concept_index < len(queue) and isinstance(queue[concept_index], dict) else {}
        if concept:
            visual_brief = concept.get("visual_brief", "") or concept.get("visual brief", "")
        prompt = f"{self.config.agent.image_instructions} Pinterest product poster background. Product: {product.get('title', self.config.agent.product_title or 'digital product')}. Goal: {goal}. Visual direction: {visual_brief}. Trend signal to reinterpret, not copy: {self._trend_context(trends or {})}. Make the image original, editorial, polished, high contrast, and leave clear space for exact text overlay. No words, logos, watermarks, or lettering in the generated image."
        output_path = output_dir / f"pinrin_generated_pin_{concept_index + 1}.png"
        output = GradioMCPImageProvider(self.config.agent.image_provider_url, self.config.agent.huggingface_token).generate(prompt, output_path, self.config.agent.image_aspect_ratio, self.config.agent.image_steps)
        result = {"status": "generated", "images": [output], "prompt": prompt}
        self.emit("image_generator", "completed", "Pinterest creative generated and ready for QA.", result)
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
