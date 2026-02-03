# app/api/main.py
from fastapi import FastAPI
from settings import settings
from routes import submit, status, results

app = FastAPI(
    title=settings.API_TITLE,
    version=settings.API_VERSION,
)

app.include_router(submit.router, prefix="/jobs", tags=["jobs"])
app.include_router(status.router, prefix="/jobs", tags=["jobs"])
app.include_router(results.router, prefix="/jobs", tags=["jobs"])

@app.get("/health")
def health():
    return {"status": "ok"}
