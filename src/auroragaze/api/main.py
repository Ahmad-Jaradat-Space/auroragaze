from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from auroragaze.api.routes import router

app = FastAPI(title="AuroraGaze", version="1.0")
app.include_router(router, prefix="/api")

_FRONTEND = Path(__file__).resolve().parents[3] / "frontend"


@app.get("/")
async def index() -> FileResponse:
    return FileResponse(_FRONTEND / "index.html")


app.mount("/static", StaticFiles(directory=_FRONTEND), name="static")
