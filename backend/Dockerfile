# 1. Base Image
FROM python:3.11-slim

# 2. Set Environment Variables
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV UV_LINK_MODE=copy
ENV UV_HTTP_TIMEOUT=300

# 3. Set Work Directory
WORKDIR /app

# 4. Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv

# 5. Copy project files and install dependencies
# Note: uv.lock should be committed to your repository
COPY pyproject.toml uv.lock* ./

# Install dependencies using uv
RUN --mount=type=cache,target=/root/.cache/uv uv sync --frozen --no-dev

# 6. Copy application code
COPY ./src ./src
COPY alembic.ini ./
COPY alembic ./alembic

# 7. Expose port
EXPOSE 8000

# 8. Command to run the application
# 单 worker：FastAPI 只做 I/O 编排（CPU 密集走 Celery），与本地 dev 对齐避免 module-level lock + APScheduler 多进程问题。
CMD ["uv", "run", "uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]