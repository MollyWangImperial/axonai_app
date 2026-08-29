"""Production entry point that serves the Expo web build and FastAPI together."""

from pathlib import Path

from fastapi import HTTPException
from fastapi.responses import FileResponse

from backend.server import app


WEB_DIST = Path(__file__).resolve().parents[1] / "frontend" / "dist"
APP_SHELL_HEADERS = {
    "Cache-Control": "no-store, max-age=0, must-revalidate",
    "Pragma": "no-cache",
    "Expires": "0",
}
SERVICE_WORKER_HEADERS = {
    "Cache-Control": "no-cache, no-store, max-age=0, must-revalidate",
    "Pragma": "no-cache",
    "Expires": "0",
    "Service-Worker-Allowed": "/",
}
IMMUTABLE_ASSET_HEADERS = {
    "Cache-Control": "public, max-age=31536000, immutable",
}


@app.get("/", include_in_schema=False)
async def web_index() -> FileResponse:
    index = WEB_DIST / "index.html"
    if not index.is_file():
        raise HTTPException(status_code=503, detail="Web application has not been built")
    return FileResponse(index, headers=APP_SHELL_HEADERS)


@app.get("/{full_path:path}", include_in_schema=False)
async def web_assets_or_spa(full_path: str) -> FileResponse:
    # Unknown API routes must remain API 404s instead of returning index.html.
    if full_path == "api" or full_path.startswith("api/"):
        raise HTTPException(status_code=404, detail="API route not found")

    requested = (WEB_DIST / full_path).resolve()
    try:
        requested.relative_to(WEB_DIST.resolve())
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="File not found") from exc

    if requested.is_file():
        if full_path == "sw.js":
            return FileResponse(requested, headers=SERVICE_WORKER_HEADERS)
        if full_path.startswith("_expo/static/"):
            return FileResponse(requested, headers=IMMUTABLE_ASSET_HEADERS)
        return FileResponse(requested)

    index = WEB_DIST / "index.html"
    if not index.is_file():
        raise HTTPException(status_code=503, detail="Web application has not been built")
    return FileResponse(index, headers=APP_SHELL_HEADERS)
