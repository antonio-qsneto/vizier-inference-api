from pydantic_settings import BaseSettings  # type: ignore


class Settings(BaseSettings):
    AWS_REGION: str = "us-east-1"

    SQS_QUEUE_URL: str
    JOBS_TABLE_NAME: str
    ARTIFACTS_BUCKET: str
    JOB_ARTIFACTS_PREFIX: str = "jobs"

    PRESIGNED_URL_EXPIRY_SECONDS: int = 3600
    DEFAULT_REQUESTED_DEVICE: str = "cuda"
    DEFAULT_SLICE_BATCH_SIZE: int | None = None

    API_TITLE: str = "Vizier Inference API"
    API_VERSION: str = "2.0.0"
    API_AUTH_ENABLED: bool = True
    API_AUTH_BEARER_TOKEN: str | None = None

    class Config:
        env_file = ".env"


settings = Settings()
