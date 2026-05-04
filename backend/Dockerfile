ARG PYTHON_VERSION=3.11

FROM python:${PYTHON_VERSION}-slim AS base

ENV LANG=C.UTF-8 \
    LC_ALL=C.UTF-8 \
    PATH="/.venv/bin:$PATH" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN set -ex && \
    sed -i 's/deb.debian.org/mirrors.cloud.tencent.com/g' /etc/apt/sources.list.d/debian.sources && \
    apt update

FROM base AS builder

WORKDIR /

COPY requirements.txt .

RUN set -ex && \
    mkdir ~/.pip && \
    echo "[global]" >> ~/.pip/pip.conf && \
    echo "index-url=https://mirrors.tencent.com/pypi/simple/" >> ~/.pip/pip.conf

RUN set -ex && \
    python -m venv .venv && \
    pip install --upgrade pip && \
    pip install -r ./requirements.txt

FROM base

WORKDIR /app

COPY --from=builder /.venv /.venv
ADD ./ ./

ENV CODEX_CLI_PATH="codex" \
    CODEX_CLI_MODEL="gpt-5.5" \
    CODEX_CLI_REASONING_EFFORT="xhigh" \
    LOCAL_UPLOAD_DIR="local_storage/uploads" \
    ASR_PROVIDER="faster-whisper" \
    ASR_LANGUAGE="auto" \
    FASTER_WHISPER_MODEL="small" \
    FASTER_WHISPER_DEVICE="auto" \
    FASTER_WHISPER_COMPUTE_TYPE="auto"

EXPOSE 8080

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8080"]
