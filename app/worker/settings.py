from pydantic_settings import BaseSettings  # type: ignore


class Settings(BaseSettings):
    AWS_REGION: str = "us-east-1"

    SQS_QUEUE_URL: str
    JOBS_TABLE_NAME: str
    ARTIFACTS_BUCKET: str

    ECS_CLUSTER: str
    BIO_TASK_DEF: str
    BIO_CONTAINER_NAME: str = "biomedparse"

    TASK_SUBNETS: str
    TASK_SECURITY_GROUPS: str
    CAPACITY_PROVIDER: str

    SQS_WAIT_SECONDS: int = 20
    ECS_TASK_POLL_SECONDS: int = 15
    PRESIGNED_URL_EXPIRY_SECONDS: int = 3600
    SQS_VISIBILITY_EXTENSION_SECONDS: int = 300
    DEFAULT_REQUESTED_DEVICE: str = "cuda"


settings = Settings()
