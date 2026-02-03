from pydantic_settings import BaseSettings # type: ignore

class Settings(BaseSettings):
    AWS_REGION: str = "us-east-1"

    SQS_QUEUE_URL: str

    # Job storage
    JOB_BASE_DIR: str = "/mnt/efs/jobs"

    # ECS
    ECS_CLUSTER: str                 # vizier-dev
    BIO_TASK_DEF: str                # ARN or family: vizier-biomedparse
    BIO_CONTAINER_NAME: str = "biomedparse"

    TASK_SUBNETS: str                # comma-separated
    TASK_SECURITY_GROUPS: str        # comma-separated
    CAPACITY_PROVIDER: str           # gpu capacity provider name

    SQS_WAIT_SECONDS: int = 20

settings = Settings()
