# ============================================================
# Tiger Dashboard — Web 看板（FastAPI + tigeropen SDK）
# ============================================================

FROM python:3.11-slim

LABEL maintainer="yuuka"
LABEL description="Tiger Trading Dashboard (FastAPI)"

ENV TZ=Asia/Shanghai
RUN ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone

WORKDIR /app

# 构建上下文是项目根目录，所以用 dashboard/ 前缀
COPY dashboard/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY dashboard/ /app/dashboard/
# 静态文件
COPY dashboard/static/ /app/dashboard/static/

EXPOSE 8088

CMD ["uvicorn", "dashboard.main:app", "--host", "0.0.0.0", "--port", "8088"]
