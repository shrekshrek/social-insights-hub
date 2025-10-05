# 1. Base Image
FROM python:3.11-slim

# 2. Set Environment Variables
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV UV_LINK_MODE=copy

# 3. Set Work Directory
WORKDIR /app

# 4. Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv

# 5. Copy project files and install dependencies
# Note: uv.lock should be committed to your repository
COPY pyproject.toml uv.lock* ./

# Install dependencies using uv
RUN uv sync --frozen --no-dev

# 安装 Playwright 浏览器依赖
RUN uv run playwright install --with-deps chromium

# 6. 创建非 root 用户
RUN groupadd --system app \
    && useradd --system --gid app --create-home app

# 7. Copy application code
COPY --chown=app:app ./src ./src

# 8. 调整权限，确保运行用户可写
RUN chown -R app:app /app

# 9. 切换到非 root 用户
USER app

# 10. Expose port
EXPOSE 8000

# 11. Command to run the application
# Use uv to run the application
CMD ["uv", "run", "gunicorn", "-w", "4", "-k", "uvicorn.workers.UvicornWorker", "-b", "0.0.0.0:8000", "src.main:app"]
