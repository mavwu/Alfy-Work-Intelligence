from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .bootstrap import ensure_defaults
from .db import SessionLocal, init_db
from .routers import chat, dashboard, imports, projects, repositories, reports, system, timeline, work

app = FastAPI(title="Alfy Work Intelligence", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:5173", "http://localhost:5173"],
    allow_origin_regex=r"^http://(127\.0\.0\.1|localhost):\d+$",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(system.router, prefix="/api", tags=["system"])
app.include_router(projects.router, prefix="/api", tags=["projects"])
app.include_router(repositories.router, prefix="/api", tags=["repositories"])
app.include_router(work.router, prefix="/api", tags=["work"])
app.include_router(imports.router, prefix="/api", tags=["imports"])
app.include_router(timeline.router, prefix="/api", tags=["timeline"])
app.include_router(reports.router, prefix="/api", tags=["reports"])
app.include_router(chat.router, prefix="/api", tags=["chat"])
app.include_router(dashboard.router, prefix="/api", tags=["dashboard"])


@app.on_event("startup")
def startup():
    init_db()
    db = SessionLocal()
    try:
        ensure_defaults(db)
    finally:
        db.close()


@app.get("/")
def root():
    return {"name": "Alfy Work Intelligence", "status": "running"}
