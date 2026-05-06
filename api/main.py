"""PaperPilot FastAPI entrypoint."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

from api.routes import analyze as analyze_routes
from api.routes import extract as extract_routes
from api.routes import reading as reading_routes
from api.routes import translate as translate_routes

load_dotenv()

app = FastAPI(title="PaperPilot API", version="0.1.0")
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
