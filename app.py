"""
PinPilot Web App - FastAPI Server
Upload a product and the app handles everything:
Gumroad listing + Pinterest Pin publishing + tracking
"""
import json
import logging
import os
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, File, Form, UploadFile, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from pinpilot.config import Config
from pinpilot.gumroad_client import GumroadClient
from pinpilot.pinterest_client import PinterestClient
from pinpilot.tracker import PublishTracker, PublishRecord
from pinpilot.orchestrator import Orchestrator
from pinpilot.agents import HuggingFaceAdapter

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("pinpilot.webapp")

app = FastAPI(title="PinPilot", description="Automated Pinterest to Gumroad Pipeline")

BASE_DIR = Path(__file__).parent
UPLOAD_DIR = BASE_DIR / "uploads"
UPLOAD_DIR.mkdir(exist_ok=True)

app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")
app.mount("/uploads", StaticFiles(directory=str(UPLOAD_DIR)), name="uploads")

config = Config.from_env()
tracker = PublishTracker()
orchestrator = Orchestrator(config=config, store=None)
PINRIN_API_KEY = os.getenv("PINRIN_API_KEY", "")
frontend_origins = [origin.strip() for origin in os.getenv("FRONTEND_ORIGINS", "http://localhost:8000,http://localhost:3000").split(",") if origin.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=frontend_origins,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def resume_persistent_schedule() -> None:
    if orchestrator.store.get_schedule(config.agent.schedule_interval_hours)["running"]:
        orchestrator.start_schedule()


def current_user(request: Request) -> str:
    """Resolve an authenticated user when API protection is configured."""
    if PINRIN_API_KEY and request.headers.get("x-pinrin-api-key") != PINRIN_API_KEY:
        raise HTTPException(status_code=401, detail="Missing or invalid Pinrin API key")
    return request.headers.get("x-pinrin-user", "default")[:120]


@app.get("/", response_class=HTMLResponse)
async def index():
    html_path = BASE_DIR / "static" / "index.html"
    return HTMLResponse(content=html_path.read_text(encoding="utf-8"))


@app.get("/favicon.ico")
async def favicon():
    return FileResponse(BASE_DIR / "static" / "pinrin-logo.png", media_type="image/png")


@app.get("/api/status")
async def api_status():
    summary = tracker.get_summary()
    issues = config.validate()
    return {
        "status": "ok",
        "config_issues": issues,
        "publishing": summary,
        "gumroad_configured": config.gumroad.is_configured,
        "pinterest_configured": config.pinterest.is_configured,
        "agent": {
            "campaign_configured": bool(config.agent.campaign_goal),
            "huggingface_configured": bool(config.agent.huggingface_token),
            "schedule": orchestrator.schedule_status(),
            "auth_required": bool(PINRIN_API_KEY),
        },
    }


@app.post("/api/agent/run")
async def start_agent_run(request: Request):
    """Start an autonomous run using server configuration only."""
    return orchestrator.start(current_user(request))


@app.get("/api/agent/runs/{run_id}")
async def get_agent_run(run_id: str, request: Request):
    run = orchestrator.store.get(run_id, current_user(request))
    if not run:
        raise HTTPException(status_code=404, detail="Agent run not found")
    return run


@app.post("/api/agent/runs/{run_id}/approve-opportunity")
async def approve_agent_opportunity(run_id: str, request: Request):
    run = orchestrator.approve_opportunity(run_id, current_user(request))
    if not run:
        raise HTTPException(status_code=404, detail="Agent run not found")
    return run


@app.post("/api/agent/runs/{run_id}/approve-publish")
async def approve_agent_publish(run_id: str, request: Request):
    run = orchestrator.approve_publish(run_id, current_user(request))
    if not run:
        raise HTTPException(status_code=404, detail="Agent run not found")
    return run


@app.post("/api/agent/schedule/start")
async def start_agent_schedule(request: Request):
    current_user(request)
    return orchestrator.start_schedule()


@app.post("/api/agent/schedule/stop")
async def stop_agent_schedule(request: Request):
    current_user(request)
    return orchestrator.stop_schedule()


@app.get("/api/agent/schedule")
async def get_agent_schedule():
    return orchestrator.schedule_status()


@app.get("/api/agent/providers")
async def verify_agent_providers():
    return {"reasoning": HuggingFaceAdapter(config).health(), "image_generation": {"status": "external_provider_not_configured"}}


@app.get("/api/products")
async def list_products(request: Request):
    user_id = current_user(request)
    records = [record for record in tracker.data.records if record.user_id == user_id]
    products = {}
    for r in records:
        if r.product_name not in products:
            products[r.product_name] = {
                "name": r.product_name,
                "title": r.pin_title,
                "gumroad_url": r.gumroad_url,
                "pins": [],
                "published_at": r.published_at,
            }
        products[r.product_name]["pins"].append({
            "pin_id": r.pin_id,
            "pin_url": r.pin_url,
            "title": r.pin_title,
            "status": r.status,
        })
    return {"products": list(products.values())}



@app.get("/api/boards")
async def get_boards():
    if config.pinterest.is_configured:
        try:
            pinterest = PinterestClient(config.pinterest)
            boards = pinterest.list_boards()
            return {"boards": boards}
        except Exception as e:
            return {"boards": [], "error": str(e)}
    return {"boards": []}


@app.post("/api/generate-variations")
async def generate_variations(payload: dict):
    title = payload.get("title", "")
    tags = payload.get("tags", "")
    price = payload.get("price", "")
    
    tag_list = [t.strip() for t in tags.split(",") if t.strip()]
    tag_str = " ".join(f"#{t.replace(' ', '')}" for t in tag_list[:5])
    
    templates = [
        (
            f"? The Ultimate {title} (Instant Download)",
            f"Get organized and level up with this {title}! Fully customizable digital download for just {price}. Tap to grab yours now. {tag_str}"
        ),
        (
            f"Save Hours with {title} | aesthetic and minimal",
            f"Stop starting from scratch! This {title} is designed to make your life effortless. Instant access on Gumroad. {tag_str}"
        ),
        (
            f"Must-Have {title} ? Best Seller",
            f"Everything you need in one clean package. Designed for perfection and ease of use. Download today for {price}! {tag_str}"
        ),
    ]
    variations = [{"pin_title": t, "pin_description": d} for t, d in templates]
    return {"variations": variations}


@app.post("/api/upload")
async def upload_product(
    request: Request,
    product_file: UploadFile = File(...),
    pin_images: list[UploadFile] = File(...),
    title: str = Form(...),
    description: str = Form(...),
    price: str = Form(...),
    tags: str = Form(""),
    board_name: str = Form(""),
    pin_variations: str = Form("[]"),
):
    """Upload a product. The app handles:
    1. Save files locally
    2. Create Gumroad listing
    3. Publish Pinterest Pins
    4. Track everything
    """
    user_id = current_user(request)
    product_id = str(uuid.uuid4())[:8]
    product_dir = UPLOAD_DIR / product_id
    product_dir.mkdir(parents=True, exist_ok=True)

    results = {
        "product_id": product_id,
        "steps": [],
        "gumroad_url": None,
        "pins_created": 0,
        "errors": [],
    }

    # Step 1: Save product file
    try:
        product_path = product_dir / product_file.filename
        with open(product_path, "wb") as f:
            content = await product_file.read()
            f.write(content)
        results["steps"].append({"step": "File saved", "status": "success", "file": product_file.filename})
    except Exception as e:
        results["errors"].append(f"Failed to save product file: {e}")
        return JSONResponse(status_code=500, content=results)

    # Step 2: Save pin images
    saved_images = []
    for img in pin_images:
        try:
            img_path = product_dir / img.filename
            with open(img_path, "wb") as f:
                img_content = await img.read()
                f.write(img_content)
            saved_images.append(str(img_path))
            results["steps"].append({"step": f"Pin image saved: {img.filename}", "status": "success"})
        except Exception as e:
            results["errors"].append(f"Failed to save image {img.filename}: {e}")

    if not saved_images:
        results["errors"].append("No pin images were saved")
        return JSONResponse(status_code=400, content=results)

    # Step 3: Create Gumroad listing
    gumroad_url = None
    price_cents = int(float(price.replace("$", "").strip()) * 100)
    tag_list = [t.strip() for t in tags.split(",") if t.strip()]

    if config.gumroad.access_token and config.gumroad.access_token != "your_gumroad_access_token_optional":
        try:
            gumroad = GumroadClient(config.gumroad)
            product = gumroad.create_product(
                name=title,
                description=description,
                price=price_cents,
                product_file=str(product_path),
                tags=tag_list,
            )
            gumroad_url = product.url
            results["gumroad_url"] = gumroad_url
            results["steps"].append({"step": "Gumroad listing created", "status": "success", "url": gumroad_url})
        except Exception as e:
            results["errors"].append(f"Gumroad listing failed: {e}")
            results["steps"].append({"step": "Gumroad listing", "status": "failed", "error": str(e)})
    else:
        results["steps"].append({"step": "Gumroad listing", "status": "skipped", "reason": "No Gumroad API token configured"})
        gumroad_url = config.gumroad.store_url or "https://gumroad.com"

    # Step 4: Publish Pinterest Pins
    if config.pinterest.is_configured:
        try:
            pinterest = PinterestClient(config.pinterest)

            # Resolve board
            board_id = config.pinterest.board_id
            if board_name:
                board_id = pinterest.get_or_create_board(board_name)

            # Parse variations
            try:
                variations = json.loads(pin_variations)
            except json.JSONDecodeError:
                variations = []

            if not variations:
                tag_str = " ".join(f"#{t.replace(' ', '')}" for t in tag_list[:5])
                variations = [{"pin_title": title, "pin_description": f"{description} {tag_str}".strip()}]

            pins_created = 0
            for img_path in saved_images:
                for var in variations:
                    pin_title = var.get("pin_title", title)
                    pin_desc = var.get("pin_description", description)

                    result = pinterest.create_pin_from_file(
                        title=pin_title,
                        description=pin_desc,
                        image_path=img_path,
                        link=gumroad_url or "",
                        board_id=board_id,
                    )

                    if result.success:
                        pins_created += 1
                        record = PublishRecord(
                            dedup_key=f"{product_id}|{Path(img_path).name}|{pin_title}",
                            product_name=title,
                            pin_id=result.pin_id or "",
                            pin_url=result.pin_url or "",
                            pin_title=pin_title,
                            gumroad_url=gumroad_url or "",
                        image_path=img_path,
                        board_id=board_id,
                        published_at=datetime.now(timezone.utc).isoformat(),
                        user_id=user_id,
                        )
                        tracker.record(record)
                        results["steps"].append({"step": f"Pin published: {pin_title[:40]}...", "status": "success", "pin_url": result.pin_url})
                    else:
                        results["errors"].append(f"Pin failed: {result.error}")

            results["pins_created"] = pins_created
        except Exception as e:
            results["errors"].append(f"Pinterest publishing failed: {e}")
            results["steps"].append({"step": "Pinterest publishing", "status": "failed", "error": str(e)})
    else:
        results["steps"].append({"step": "Pinterest publishing", "status": "skipped", "reason": "Pinterest not configured"})

    # Save product metadata
    metadata = {
        "product_id": product_id,
        "title": title,
        "description": description,
        "price": price,
        "tags": tag_list,
        "board": board_name,
        "gumroad_url": gumroad_url,
        "product_file": product_file.filename,
        "pin_images": [Path(p).name for p in saved_images],
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    meta_path = product_dir / "product.json"
    meta_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")

    status_code = 200 if not results["errors"] else 207
    return JSONResponse(status_code=status_code, content=results)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=True)
