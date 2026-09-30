"""FastAPI app — endpoints, startup warm-up, health check."""
from __future__ import annotations

import asyncio
import logging
import time
from contextlib import asynccontextmanager

import orjson
from fastapi import FastAPI, HTTPException
from fastapi.responses import ORJSONResponse

from app.envelope import TroubleshootRequest, TroubleshootResponse, MetaInfo
from app.pipeline import get_pipeline
from app.loader import load_siis_responses
from schema import ContextDeeplinkResponse

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

# ── Startup state ─────────────────────────────────────────────────────
_ready = False


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup: initialize pipeline and prewarm cache."""
    global _ready
    logger.info("Starting up — initializing pipeline...")

    pipeline = get_pipeline()

    # Run initialization in a thread to not block the event loop
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, pipeline.initialize)

    # Prewarm with all 20 rows
    rows = load_siis_responses()
    await loop.run_in_executor(None, pipeline.prewarm, rows)

    _ready = True
    logger.info("Startup complete — ready to serve requests")
    yield
    logger.info("Shutting down")


from pathlib import Path
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(
    title="Smart Guided Troubleshooting Engine",
    version="1.0.0",
    default_response_class=ORJSONResponse,
    lifespan=lifespan,
)

# Enable CORS for browser integration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health():
    """Health check — returns 200 only when fully loaded."""
    if not _ready:
        raise HTTPException(status_code=503, detail="Not ready")
    return {"status": "ok"}


@app.post("/v1/troubleshoot")
@app.post("/troubleshoot")
async def troubleshoot(request: TroubleshootRequest):
    """Main troubleshooting endpoint.

    Body: {"query": str, "siis_response": str | {title, content} | null}
    """
    if not _ready:
        raise HTTPException(status_code=503, detail="Service not ready")

    pipeline = get_pipeline()

    # Parse siis_response to pass to pipeline
    siis = request.siis_response
    if isinstance(siis, str):
        siis_input = siis
    elif siis is not None:
        siis_input = {"title": siis.title, "content": siis.content}
    else:
        siis_input = None

    # Run pipeline in executor to not block event loop
    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(
        None, pipeline.process_query, request.query, siis_input
    )

    return ORJSONResponse(content=result)


# Mount frontend static assets from frontend/TroubleShoot
FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend" / "TroubleShoot"
if FRONTEND_DIR.exists():
    app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")

