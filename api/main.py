"""PaperPilot FastAPI entrypoint."""

import logging
import time

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.requests import Request

from api.routes import analyze as analyze_routes
from api.routes import extract as extract_routes
from api.routes import reading as reading_routes
from api.routes import translate as translate_routes
from services.log_config import ensure_paperpilot_logging

load_dotenv()

ensure_paperpilot_logging(service="api")
_http_log = logging.getLogger("paperpilot.api.http")

app = FastAPI(title="PaperPilot API", version="0.1.0")


@app.middleware("http")
async def paperpilot_request_log_middleware(request: Request, call_next):
    t0 = time.perf_counter()
    try:
        response = await call_next(request)
    except Exception:
        _http_log.exception("%s %s", request.method, request.url.path)
        raise
    elapsed_ms = (time.perf_counter() - t0) * 1000
    path = request.url.path
    code = response.status_code
    if code >= 400:
        _http_log.warning("%s %s -> %s %.1fms", request.method, path, code, elapsed_ms)
    else:
        _http_log.info("%s %s -> %s %.1fms", request.method, path, code, elapsed_ms)
    return response


app.include_router(extract_routes.router)
app.include_router(reading_routes.router)
app.include_router(analyze_routes.router)
app.include_router(translate_routes.router)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://127.0.0.1:8501",
        "http://localhost:8501",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health():
    return {"ok": True, "service": "paperpilot-api"}
