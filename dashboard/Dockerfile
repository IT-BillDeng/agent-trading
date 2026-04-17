# ============================================================
# Agent Dashboard — Web 看板 + 内置信号调度器
# ============================================================

FROM python:3.11-slim

LABEL maintainer="main-agent"
LABEL description="Agent Trading Dashboard (FastAPI + Signal Scheduler)"

ENV TZ=Asia/Shanghai
RUN ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone

WORKDIR /app

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

# Runtime / logs 目录
RUN mkdir -p /app/runtime/logs /app/runtime/state /app/logs/audit /app/logs/service /app/logs/agents /app/logs/latest /app/logs/manifests

EXPOSE 8088

CMD ["uvicorn", "dashboard.main:app", "--host", "0.0.0.0", "--port", "8088"]
