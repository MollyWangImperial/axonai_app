FROM node:20-bookworm-slim AS web-build

WORKDIR /app/frontend
RUN corepack enable

COPY frontend/package.json frontend/yarn.lock ./
COPY frontend/scripts ./scripts
RUN yarn install --frozen-lockfile --ignore-scripts

COPY frontend/ ./
ENV EXPO_PUBLIC_BACKEND_URL=""
RUN yarn build:web


FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8000

WORKDIR /app

COPY backend/requirements-deploy.txt ./backend/requirements-deploy.txt
RUN pip install --no-cache-dir -r backend/requirements-deploy.txt

COPY backend/ ./backend/
COPY --from=web-build /app/frontend/dist ./frontend/dist

EXPOSE 8000

CMD ["sh", "-c", "uvicorn backend.deploy_server:app --host 0.0.0.0 --port ${PORT}"]
