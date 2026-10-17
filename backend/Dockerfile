# API and worker image. Build from the repository root (task-type configs live there):
#   docker build -f backend/Dockerfile -t agent-onboarding .
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 \
    ENV=production INLINE_WORKER=false

WORKDIR /srv/backend
COPY backend/pyproject.toml ./
COPY backend/app ./app
RUN pip install .

COPY backend/alembic.ini ./
COPY backend/migrations ./migrations
COPY task_types /srv/task_types

RUN useradd --create-home --uid 10001 app
USER app

EXPOSE 8000
# The worker process overrides this with: python -m app.worker
CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers"]
