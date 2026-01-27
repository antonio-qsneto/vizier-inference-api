FROM python:3.10-slim

# ---- System deps ----
RUN apt-get update && apt-get install -y \
    docker.io \
    curl \
    && rm -rf /var/lib/apt/lists/*

# ---- Python deps ----
RUN pip install --no-cache-dir \
    boto3 \
    python-dotenv

# ---- App code ----
WORKDIR /app
COPY app /app/app


# ---- Runtime ----
ENV PYTHONPATH=/app
ENV AWS_REGION=us-east-1

# Entry point = worker loop
CMD ["python", "-m", "app.worker.worker"]
