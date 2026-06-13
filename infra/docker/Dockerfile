# syntax=docker/dockerfile:1.7
# ---- Builder ----
FROM python:3.12-slim AS builder

ENV PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONDONTWRITEBYTECODE=1

RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential libpq-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build
# hatchling needs pyproject, README (referenced as project readme), and the
# package source itself present BEFORE `pip install .` can build the wheel.
COPY pyproject.toml README.md ./
COPY app ./app
RUN pip install --upgrade pip && \
    pip install --prefix=/install .

# ---- Runtime ----
FROM python:3.12-slim AS runtime

# /install/lib/... must be on PYTHONPATH: --prefix installs OUTSIDE the
# interpreter's default site-packages.
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/install/bin:${PATH}" \
    PYTHONPATH="/app:/install/lib/python3.12/site-packages"

RUN apt-get update && apt-get install -y --no-install-recommends \
        libpq5 curl tini \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --uid 10001 --create-home --shell /usr/sbin/nologin app

COPY --from=builder /install /install
WORKDIR /app
COPY app /app/app
COPY migrations /app/migrations
COPY scripts /app/scripts

USER 10001:10001

EXPOSE 8000
HEALTHCHECK --interval=15s --timeout=3s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
