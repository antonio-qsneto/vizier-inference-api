# app/api/settings.py

from pydantic_settings import BaseSettings # type: ignore

class Settings(BaseSettings):
    # AWS
    AWS_REGION: str = "us-east-1"

    # SQS (AWS-managed, no LocalStack)
    SQS_QUEUE_URL: str

    # Storage (EFS)
    JOB_BASE_DIR: str = "/mnt/efs/jobs"
    # Backward-compat alias used in routes/services
    @property
    def JOBS_ROOT(self) -> str:
        return self.JOB_BASE_DIR

    # API
    API_TITLE: str = "Vizier Inference API"
    API_VERSION: str = "1.0.0"

    class Config:
        env_file = ".env"

settings = Settings()
