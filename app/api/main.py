from fastapi import FastAPI

from routes import jobs, results, status, submit
from settings import settings

app = FastAPI(
    title=settings.API_TITLE,
    version=settings.API_VERSION,
)

app.include_router(jobs.router, prefix="/jobs", tags=["jobs"])
app.include_router(submit.router, prefix="/jobs", tags=["jobs"])
app.include_router(status.router, prefix="/jobs", tags=["jobs"])
app.include_router(results.router, prefix="/jobs", tags=["jobs"])


@app.get("/health")
def health():
    return {"status": "ok", "version": settings.API_VERSION}
