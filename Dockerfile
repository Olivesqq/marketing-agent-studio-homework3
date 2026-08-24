FROM node:22-alpine AS frontend-build
WORKDIR /workspace/frontend
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.12-slim AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1
WORKDIR /workspace
RUN groupadd --system app && useradd --system --gid app --home-dir /workspace app
COPY backend/requirements.txt /workspace/backend/requirements.txt
RUN pip install --upgrade pip && pip install -r /workspace/backend/requirements.txt
COPY backend/ /workspace/backend/
COPY --from=frontend-build /workspace/frontend/dist /workspace/frontend/dist
RUN mkdir -p /workspace/backend/data && chown -R app:app /workspace
USER app
EXPOSE 8000
CMD ["sh", "-c", "cd /workspace/backend && uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --proxy-headers --forwarded-allow-ips='*'"]
