FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ca-certificates \
        libpq5 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./
RUN pip install --upgrade pip \
    && pip install -r requirements.txt

COPY . .

RUN chmod +x /app/docker/entrypoint.sh \
    && groupadd --gid 10001 echocall \
    && useradd --uid 10001 --gid 10001 --no-create-home --shell /usr/sbin/nologin echocall

USER 10001:10001

ENTRYPOINT ["/app/docker/entrypoint.sh"]
