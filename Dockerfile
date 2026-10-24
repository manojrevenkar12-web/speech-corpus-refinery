# One image for every job (crawl, work, release, setup) and the API with its review console.

FROM node:22-slim AS web
WORKDIR /web
COPY web/package.json web/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY web/ ./
RUN npm run build

FROM python:3.12-slim AS app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 SCR_HOME=/app PIP_NO_CACHE_DIR=1
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg libgomp1 && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY pyproject.toml README.md ./
COPY src/ src/
RUN pip install .
COPY config/ config/
# Pinned models and corpora (sha256-checked against config/assets.yaml), baked in so jobs start
# without downloading anything; the protected evaluation set is fingerprinted from these.
RUN scr fetch
COPY --from=web /web/dist web/dist
RUN useradd --uid 10001 --create-home scr && chown -R scr /app/data
USER 10001
EXPOSE 8080
ENTRYPOINT ["scr"]
CMD ["serve", "--host", "0.0.0.0", "--port", "8080"]
