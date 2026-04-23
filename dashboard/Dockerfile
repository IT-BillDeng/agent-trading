# ============================================================
# Agent Dashboard — Web 看板 + 内置信号调度器
# ============================================================

FROM python:3.11-slim AS base

LABEL maintainer="main-agent"
LABEL description="Agent Trading Dashboard (FastAPI + Signal Scheduler)"

ENV TZ=Asia/Shanghai
RUN ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone

WORKDIR /app
ENV PYTHONPATH=/app:/app/system/engine/src

# Dashboard 依赖
COPY dashboard/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

# Engine 依赖（调度器需要）
COPY system/engine/requirements.txt /app/engine-requirements.txt
RUN pip install --no-cache-dir -r /app/engine-requirements.txt

# Dashboard 代码 + 静态文件
COPY dashboard/ /app/dashboard/
COPY dashboard/static/ /app/dashboard/static/

# Engine 源码（调度器导入使用）
COPY system/engine/src/ /app/system/engine/src/
COPY factors/ /app/factors/

# Runtime / logs 目录
RUN mkdir -p /app/runtime/logs /app/runtime/state /app/logs/audit /app/logs/service /app/logs/agents /app/logs/latest /app/logs/manifests

FROM base AS runtime

RUN pip install --no-cache-dir pytest

COPY tests/ /app/tests/
COPY system/engine/tests/ /app/system/engine/tests/
COPY scripts/ /app/scripts/
COPY specs/ /app/specs/
COPY experiments/ /app/experiments/
COPY agents/ /app/agents/
COPY cron/ /app/cron/
COPY docs/ /app/docs/
COPY README.md /app/README.md

EXPOSE 8088

CMD ["uvicorn", "dashboard.main:app", "--host", "0.0.0.0", "--port", "8088"]

FROM base AS test-runner

RUN pip install --no-cache-dir pytest

COPY tests/ /app/tests/
COPY system/engine/tests/ /app/system/engine/tests/
COPY scripts/ /app/scripts/
COPY specs/ /app/specs/
COPY experiments/ /app/experiments/
COPY rules/ /app/rules/
COPY config/ /app/config/
COPY agents/ /app/agents/
COPY cron/ /app/cron/
COPY docs/ /app/docs/
COPY README.md /app/README.md

CMD ["python", "-m", "pytest", "-q"]
