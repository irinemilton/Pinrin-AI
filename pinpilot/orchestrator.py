"""Persistent autonomous campaign orchestration and scheduling."""
from __future__ import annotations

import json
import hashlib
import logging
import sqlite3
import threading
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .agents import AgentBlocked, AgentSuite
from .artifacts import render_product_files, validate_product_files
from .config import Config
from .gumroad_client import GumroadClient
from .pinterest_client import PinterestClient
from .tracker import PublishRecord, PublishTracker

logger = logging.getLogger("pinpilot.orchestrator")
RUNS_PATH = Path("pinpilot.sqlite3")


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


class RunStore:
    def __init__(self, path: Path = RUNS_PATH):
        self.path = path
        self.lock = threading.RLock()
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=30, check_same_thread=False)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode=WAL")
        return connection

    @contextmanager
    def _session(self):
        connection = self._connect()
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def _init_db(self) -> None:
        with self._session() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS runs (
                    id TEXT PRIMARY KEY, user_id TEXT NOT NULL, goal TEXT NOT NULL,
                    status TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
                    approval_required INTEGER NOT NULL DEFAULT 0, artifacts TEXT NOT NULL DEFAULT '{}', error TEXT
                );
                CREATE TABLE IF NOT EXISTS events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, run_id TEXT NOT NULL, agent TEXT NOT NULL,
                    status TEXT NOT NULL, summary TEXT NOT NULL, data TEXT NOT NULL DEFAULT '{}', created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS agent_states (
                    run_id TEXT NOT NULL, agent TEXT NOT NULL, status TEXT NOT NULL,
                    summary TEXT NOT NULL, updated_at TEXT NOT NULL, PRIMARY KEY(run_id, agent)
                );
                CREATE TABLE IF NOT EXISTS locks (run_id TEXT PRIMARY KEY, owner TEXT NOT NULL, acquired_at TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS schedules (id INTEGER PRIMARY KEY CHECK(id=1), running INTEGER NOT NULL, interval_hours INTEGER NOT NULL, updated_at TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS artifacts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, run_id TEXT NOT NULL, path TEXT NOT NULL,
                    kind TEXT NOT NULL, sha256 TEXT NOT NULL, created_at TEXT NOT NULL
                );
            """)

    def create(self, goal: str, user_id: str = "default") -> dict[str, Any]:
        run_id = f"campaign_{uuid.uuid4().hex[:10]}"
        timestamp = now()
        with self.lock, self._session() as db:
            db.execute("INSERT INTO runs(id,user_id,goal,status,created_at,updated_at) VALUES(?,?,?,?,?,?)", (run_id, user_id, goal, "queued", timestamp, timestamp))
        return self.get(run_id, user_id) or {}

    def has_active(self, user_id: str) -> bool:
        with self.lock, self._session() as db:
            row = db.execute("SELECT 1 FROM runs WHERE user_id=? AND status IN ('queued','running','publishing') LIMIT 1", (user_id,)).fetchone()
        return bool(row)

    def get(self, run_id: str, user_id: str | None = None) -> dict[str, Any] | None:
        with self.lock, self._session() as db:
            query = "SELECT * FROM runs WHERE id=?" + (" AND user_id=?" if user_id else "")
            row = db.execute(query, (run_id, user_id) if user_id else (run_id,)).fetchone()
            if not row:
                return None
            events = [dict(item) for item in db.execute("SELECT created_at as at,agent,status,summary,data FROM events WHERE run_id=? ORDER BY id", (run_id,)).fetchall()]
            for event in events:
                event["data"] = json.loads(event["data"] or "{}")
            agents = {item["agent"]: dict(item) for item in db.execute("SELECT agent,status,summary,updated_at FROM agent_states WHERE run_id=?", (run_id,)).fetchall()}
            checksums = [dict(item) for item in db.execute("SELECT path,kind,sha256,created_at FROM artifacts WHERE run_id=? ORDER BY id", (run_id,)).fetchall()]
            return {"id": row["id"], "user_id": row["user_id"], "goal": row["goal"], "status": row["status"], "created_at": row["created_at"], "updated_at": row["updated_at"], "events": events, "agents": agents, "approval_required": bool(row["approval_required"]), "artifacts": json.loads(row["artifacts"] or "{}"), "artifact_checksums": checksums, "error": row["error"]}

    def update(self, run_id: str, **changes: Any) -> None:
        allowed = {"status", "approval_required", "artifacts", "error"}
        fields = [(key, json.dumps(value) if key == "artifacts" else int(value) if key == "approval_required" else value) for key, value in changes.items() if key in allowed]
        if not fields:
            return
        fields.append(("updated_at", now()))
        with self.lock, self._session() as db:
            db.execute(f"UPDATE runs SET {', '.join(f'{key}=?' for key, _ in fields)} WHERE id=?", [value for _, value in fields] + [run_id])

    def event(self, run_id: str, agent: str, status: str, summary: str, data: dict[str, Any] | None = None) -> None:
        timestamp = now()
        with self.lock, self._session() as db:
            db.execute("INSERT INTO events(run_id,agent,status,summary,data,created_at) VALUES(?,?,?,?,?,?)", (run_id, agent, status, summary, json.dumps(data or {}), timestamp))
            db.execute("INSERT INTO agent_states(run_id,agent,status,summary,updated_at) VALUES(?,?,?,?,?) ON CONFLICT(run_id,agent) DO UPDATE SET status=excluded.status,summary=excluded.summary,updated_at=excluded.updated_at", (run_id, agent, status, summary, timestamp))
            db.execute("UPDATE runs SET updated_at=? WHERE id=?", (timestamp, run_id))

    def acquire(self, run_id: str, owner: str) -> bool:
        try:
            with self.lock, self._session() as db:
                db.execute("INSERT INTO locks(run_id,owner,acquired_at) VALUES(?,?,?)", (run_id, owner, now()))
            return True
        except sqlite3.IntegrityError:
            return False

    def release(self, run_id: str, owner: str) -> None:
        with self.lock, self._session() as db:
            db.execute("DELETE FROM locks WHERE run_id=? AND owner=?", (run_id, owner))

    def schedule(self, running: bool, interval_hours: int) -> dict[str, Any]:
        with self.lock, self._session() as db:
            db.execute("INSERT INTO schedules(id,running,interval_hours,updated_at) VALUES(1,?,?,?) ON CONFLICT(id) DO UPDATE SET running=excluded.running,interval_hours=excluded.interval_hours,updated_at=excluded.updated_at", (int(running), interval_hours, now()))
        return {"running": running, "interval_hours": interval_hours}

    def get_schedule(self, interval_hours: int) -> dict[str, Any]:
        with self.lock, self._session() as db:
            row = db.execute("SELECT running,interval_hours FROM schedules WHERE id=1").fetchone()
        return {"running": bool(row["running"]) if row else False, "interval_hours": row["interval_hours"] if row else interval_hours}

    def record_artifact(self, run_id: str, path: Path, kind: str) -> dict[str, str]:
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        with self.lock, self._session() as db:
            db.execute("INSERT INTO artifacts(run_id,path,kind,sha256,created_at) VALUES(?,?,?,?,?)", (run_id, str(path), kind, digest, now()))
        return {"path": str(path), "kind": kind, "sha256": digest}


class Orchestrator:
    def __init__(self, config: Config | None = None, store: RunStore | None = None):
        self.config = config or Config.from_env()
        self.store = store or RunStore()
        self.tracker = PublishTracker()
        self.scheduler_stop = threading.Event()
        self.scheduler_thread: threading.Thread | None = None

    def start(self, user_id: str = "default") -> dict[str, Any]:
        goal = self.config.agent.campaign_goal.strip()
        if self.store.has_active(user_id):
            return {"status": "already_running", "message": "An active campaign already exists for this user."}
        run = self.store.create(goal, user_id)
        if not goal:
            self.store.update(run["id"], status="blocked", error="AGENT_CAMPAIGN_GOAL is not configured")
            return self.store.get(run["id"]) or run
        thread = threading.Thread(target=self._execute, args=(run["id"],), daemon=True)
        thread.start()
        return run

    def _emit(self, run_id: str, agent: str, status: str, summary: str, data: dict[str, Any] | None = None) -> None:
        self.store.event(run_id, agent, status, summary, data)

    def _retry(self, run_id: str, agent: str, operation: Any) -> Any:
        """Retry transient failures; configuration/auth blockers stop immediately."""
        attempts = max(0, self.config.agent.max_retries) + 1
        for attempt in range(attempts):
            try:
                return operation()
            except AgentBlocked:
                raise
            except Exception as exc:
                if attempt >= attempts - 1:
                    raise
                self._emit(run_id, agent, "retrying", f"Transient failure; retry {attempt + 1} of {attempts - 1}.", {"error": str(exc)})

    def _execute(self, run_id: str) -> None:
        run = self.store.get(run_id)
        if not run:
            return
        owner = f"worker_{uuid.uuid4().hex}"
        if not self.store.acquire(run_id, owner):
            return
        self.store.update(run_id, status="running")
        suite = AgentSuite(self.config, self.tracker, lambda agent, status, summary, data: self._emit(run_id, agent, status, summary, data))
        try:
            trends = self._retry(run_id, "trend_scout", lambda: suite.run_trend_scout(run["goal"]))
            opportunities = self._retry(run_id, "opportunity_analyst", lambda: suite.run_opportunity_analyst(run["goal"], trends))
            self.store.update(run_id, status="awaiting_approval", approval_required=True, artifacts={"trends": trends, "opportunities": opportunities})
        except AgentBlocked as exc:
            self._blocked(run_id, str(exc))
        except Exception as exc:
            logger.exception("Campaign %s failed", run_id)
            self._blocked(run_id, f"Orchestrator failure: {exc}")
        finally:
            self.store.release(run_id, owner)

    def approve_opportunity(self, run_id: str, user_id: str = "default") -> dict[str, Any] | None:
        run = self.store.get(run_id, user_id)
        if not run or run["status"] != "awaiting_approval":
            return run
        self.store.update(run_id, status="running", approval_required=False)
        thread = threading.Thread(target=self._continue_after_approval, args=(run_id,), daemon=True)
        thread.start()
        return self.store.get(run_id)

    def _continue_after_approval(self, run_id: str) -> None:
        run = self.store.get(run_id)
        if not run:
            return
        suite = AgentSuite(self.config, self.tracker, lambda agent, status, summary, data: self._emit(run_id, agent, status, summary, data))
        try:
            opportunity = run["artifacts"].get("opportunities", {})
            product = self._retry(run_id, "product_builder", lambda: suite.run_product_builder(run["goal"], opportunity))
            product_dir = Path("artifacts") / run_id
            if product.get("status") == "source_supplied":
                product["files"] = [{"path": product["file"], "kind": "supplied_product"}]
            else:
                title = self.config.agent.product_title or product.get("title") or "Pinrin digital product"
                product = {**product, **render_product_files(product_dir, title, run["goal"], product)}
            product["qa"] = validate_product_files(product.get("files", []), self.config.agent.pin_images)
            if not self.config.agent.pin_images:
                marketing = self._retry(run_id, "marketing_assistant", lambda: suite.run_marketing_assistant(run["goal"], product))
                generated = self._retry(run_id, "image_generator", lambda: suite.run_image_generation(run["goal"], product, marketing, product_dir))
                generated_images = [item["path"] for item in generated["images"]]
                product["qa"] = validate_product_files(product.get("files", []), generated_images)
                product["generated_images"] = generated_images
            else:
                marketing = self._retry(run_id, "marketing_assistant", lambda: suite.run_marketing_assistant(run["goal"], product))
            if product["qa"]["status"] != "passed":
                raise AgentBlocked("Product quality checks failed; review the generated files before publishing")
            product["checksums"] = [self.store.record_artifact(run_id, Path(item["path"]), item["kind"]) for item in product.get("files", [])]
            product["checksums"].extend(self.store.record_artifact(run_id, Path(path), "generated_pin") for path in product.get("generated_images", []))
            self.store.update(run_id, status="awaiting_publish_approval", approval_required=True, artifacts={**run["artifacts"], "product": product, "marketing": marketing, "generated_images": product.get("generated_images", [])})
        except AgentBlocked as exc:
            self._blocked(run_id, str(exc))
        except Exception as exc:
            logger.exception("Campaign %s failed after opportunity approval", run_id)
            self._blocked(run_id, f"Orchestrator failure: {exc}")

    def approve_publish(self, run_id: str, user_id: str = "default") -> dict[str, Any] | None:
        run = self.store.get(run_id, user_id)
        if not run or run["status"] != "awaiting_publish_approval":
            return run
        self.store.update(run_id, status="publishing", approval_required=False)
        thread = threading.Thread(target=self._publish, args=(run_id,), daemon=True)
        thread.start()
        return self.store.get(run_id)

    def _publish(self, run_id: str) -> None:
        run = self.store.get(run_id)
        if not run:
            return
        try:
            product_file = Path(self.config.agent.product_file)
            images = [Path(path) for path in self.config.agent.pin_images]
            if not images:
                images = [Path(path) for path in run.get("artifacts", {}).get("generated_images", [])]
            if not product_file.exists() or not images or not all(path.exists() for path in images):
                raise AgentBlocked("A product file and either AGENT_PIN_IMAGES or generated campaign images are required for publishing")
            input_checksums = [self.store.record_artifact(run_id, product_file, "product_source")]
            input_checksums.extend(self.store.record_artifact(run_id, image, "pin_source") for image in images)
            self.store.update(run_id, artifacts={**run["artifacts"], "input_checksums": input_checksums})
            if not self.config.gumroad.access_token:
                raise AgentBlocked("GUMROAD_ACCESS_TOKEN is required for server-side product creation")
            gumroad = GumroadClient(self.config.gumroad)
            title = self.config.agent.product_title or product_file.stem.replace("_", " ").title()
            if self.config.agent.price <= 0:
                raise AgentBlocked("AGENT_PRICE must be greater than zero for Gumroad publication")
            product = gumroad.create_product(name=title, description=run["goal"], price=self.config.agent.price, product_file=str(product_file))
            self._emit(run_id, "commerce_agent", "completed", "Gumroad returned a product URL.", {"product_id": product.id, "product_url": product.url})
            pins: list[dict[str, Any]] = []
            if not self.config.pinterest.is_configured:
                raise AgentBlocked("Pinterest access token and board ID are required for Pin publication")
            pinterest = PinterestClient(self.config.pinterest)
            for image in images:
                result = pinterest.create_pin_from_file(title=title, description=run["goal"], image_path=image, link=product.url, board_id=self.config.pinterest.board_id)
                if not result.success:
                    raise AgentBlocked(f"Pinterest publication failed: {result.error}")
                pins.append({"pin_id": result.pin_id, "pin_url": result.pin_url, "image": str(image), "published_at": now()})
                self.tracker.record(PublishRecord(dedup_key=f"{run_id}|{image.name}", product_name=title, pin_id=result.pin_id or "", pin_url=result.pin_url or "", pin_title=title, gumroad_url=product.url, image_path=str(image), board_id=self.config.pinterest.board_id, user_id=run.get("user_id", "default")))
            self._emit(run_id, "commerce_agent", "completed", "Pinterest returned verified Pin results.", {"pins": pins})
            suite = AgentSuite(self.config, self.tracker, lambda agent, status, summary, data: self._emit(run_id, agent, status, summary, data))
            performance = self._retry(run_id, "performance_analyst", suite.run_performance_analyst)
            self.store.update(run_id, status="completed", artifacts={**run["artifacts"], "publication": {"product_id": product.id, "product_url": product.url, "pins": pins}, "performance": performance})
        except AgentBlocked as exc:
            self._blocked(run_id, str(exc))
        except Exception as exc:
            logger.exception("Campaign %s publish failed", run_id)
            self._blocked(run_id, f"Publishing failure: {exc}")

    def _blocked(self, run_id: str, message: str) -> None:
        self._emit(run_id, "orchestrator", "blocked", message, None)
        self.store.update(run_id, status="blocked", error=message, approval_required=False)

    def start_schedule(self) -> dict[str, Any]:
        if self.scheduler_thread and self.scheduler_thread.is_alive():
            return {"running": True, "interval_hours": self.config.agent.schedule_interval_hours}
        self.scheduler_stop.clear()
        self.store.schedule(True, self.config.agent.schedule_interval_hours)
        self.scheduler_thread = threading.Thread(target=self._schedule_loop, daemon=True)
        self.scheduler_thread.start()
        return {"running": True, "interval_hours": self.config.agent.schedule_interval_hours}

    def stop_schedule(self) -> dict[str, Any]:
        self.scheduler_stop.set()
        self.store.schedule(False, self.config.agent.schedule_interval_hours)
        return {"running": False}

    def _schedule_loop(self) -> None:
        self.start()
        interval = max(1, self.config.agent.schedule_interval_hours) * 3600
        while not self.scheduler_stop.wait(interval):
            self.start()

    def schedule_status(self) -> dict[str, Any]:
        persisted = self.store.get_schedule(self.config.agent.schedule_interval_hours)
        return {"running": bool(self.scheduler_thread and self.scheduler_thread.is_alive()) or persisted["running"], "interval_hours": persisted["interval_hours"]}
