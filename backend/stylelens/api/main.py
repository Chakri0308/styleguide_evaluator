import logging
import mimetypes

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response

from stylelens.api.routes import guides, search
from stylelens.config import get_settings
from stylelens.storage import aget

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

app = FastAPI(title="StyleLens API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in get_settings().cors_origins.split(",") if o.strip()],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(guides.router)
app.include_router(search.router)


@app.get("/health", tags=["meta"])
async def health():
    return {"status": "ok"}


@app.get("/assets/{key:path}", tags=["meta"])
async def asset(key: str):
    """Derived assets (page renders, extracted images). Original uploads are not served here."""
    if not key.startswith("guides/") or "/original/" in key:
        raise HTTPException(404)
    try:
        data = await aget(key)
    except (FileNotFoundError, ValueError, Exception) as exc:  # noqa: BLE001
        raise HTTPException(404) from exc
    media = mimetypes.guess_type(key)[0] or "application/octet-stream"
    return Response(data, media_type=media, headers={"Cache-Control": "public, max-age=31536000, immutable"})
