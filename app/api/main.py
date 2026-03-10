from fastapi import Depends, FastAPI

from routes import jobs, results, status, submit
from security import require_api_bearer_auth
from settings import settings

app = FastAPI(
    title=settings.API_TITLE,
    version=settings.API_VERSION,
)

app.include_router(
    jobs.router,
    prefix="/jobs",
    tags=["jobs"],
    dependencies=[Depends(require_api_bearer_auth)],
)
app.include_router(
    submit.router,
    prefix="/jobs",
    tags=["jobs"],
    dependencies=[Depends(require_api_bearer_auth)],
)
app.include_router(
    status.router,
    prefix="/jobs",
    tags=["jobs"],
    dependencies=[Depends(require_api_bearer_auth)],
)
app.include_router(
    results.router,
    prefix="/jobs",
    tags=["jobs"],
    dependencies=[Depends(require_api_bearer_auth)],
)


@app.on_event("startup")
def validate_auth_configuration():
    if settings.API_AUTH_ENABLED and not (settings.API_AUTH_BEARER_TOKEN or "").strip():
        raise RuntimeError(
            "API_AUTH_ENABLED=true requires API_AUTH_BEARER_TOKEN to be configured"
        )


@app.get("/health")
def health():
    return {"status": "ok", "version": settings.API_VERSION}
