# Agent Trading — Docker 部署指南

## 快速开始

### 1. 首次部署

```bash
cd agent-trading

# 准备凭证（从旧环境复制或重新生成）
cp properties/tiger.properties.example properties/tiger.properties
# 编辑填入真实凭证
vim properties/tiger.properties

# 构建所有镜像（约 3-5 分钟）
docker compose build

# 只读连通性测试（不下单）
docker compose run --rm engine \
  python run_readonly_cycle.py \
  /app/config/app_config.docker.json \
  /app/properties/tiger.properties
```

### 2. 启动 Dashboard

```bash
# 后台启动看板
docker compose up -d dashboard

# 访问 http://localhost:8000
# 查看日志
docker compose logs -f dashboard

# 停止
docker compose down
```

### 3. OpenClaw cron 调用格式

所有 cron 任务改为通过 `docker compose run --rm` 触发：

```bash
# 只读周期
docker compose run --rm -w /app engine \
  python run_readonly_cycle.py \
  /app/config/app_config.docker.json \
  /app/properties/tiger.properties

# 策略信号周期
docker compose run --rm -w /app engine \
  python run_strategy_cycle.py \
  /app/config/app_config.docker.json \
  /app/properties/tiger.properties

# Dry-run 周期
docker compose run --rm -w /app engine \
  python run_dry_run_cycle.py \
  /app/config/app_config.docker.json \
  /app/properties/tiger.properties

# 执行周期（guarded/live 取决于配置）
docker compose run --rm -w /app engine \
  python run_execution_cycle.py \
  /app/config/app_config.docker.json \
  /app/properties/tiger.properties
```

### 4. 迁移到新机器

```bash
# 1. 安装 Docker（macOS: Docker Desktop; Ubuntu: docker.io + docker-compose-v2）
# 2. 克隆仓库
git clone git@github.com:IT-BillDeng/agent-trading.git
cd agent-trading

# 3. 准备凭证
cp properties/tiger.properties.example properties/tiger.properties
# 填入凭证

# 4. 构建（约 2 分钟，首次之后利用缓存秒建）
docker compose build

# 5. 验证
docker compose run --rm engine \
  python run_readonly_cycle.py \
  /app/config/app_config.docker.json \
  /app/properties/tiger.properties
```

### 5. 目录结构

```
agent-trading/
├── docker-compose.yml          # 编排配置（2 个服务）
├── DEPLOY.md                   # 部署指南
├── config/
│   ├── app_config.docker.json  # 容器内路径版配置
│   ├── tiger.properties        # API 凭证（.gitignore 排除）
├── rules/                      # 规则引擎配置
│   └── rules.json
├── news/                       # 新闻信息源配置
│   └── newswire_sources.json
├── properties/                 # API 凭证（gitignore）
│   ├── tiger.properties
│   └── tiger.properties.example
├── data/                       # 标的数据
│   └── watchlist.json
├── runtime/engine/       # 运行时产物（读写 mount）
│   ├── logs/
│   └── state/
├── system/engine/        # 核心执行引擎
│   ├── Dockerfile
│   ├── requirements.txt        # urllib3 + cryptography
│   └── src/engine/
├── dashboard/                  # Web 看板
│   ├── Dockerfile
│   ├── requirements.txt        # tigeropen + fastapi + uvicorn
│   └── app.py
└── docs/                       # 岗位说明、任务模板
```

### 5. 配置说明

| 文件 | 容器内路径 | 说明 |
|------|-----------|------|
| `app_config.docker.json` | `/app/config/app_config.docker.json` | 已适配容器路径的配置 |
| `tiger.properties` | `/app/properties/tiger.properties` | API 凭证 |
| `watchlist.json` | `/app/data/watchlist.json` | 共享标的清单 |

### 6. 注意事项

- **默认 guarded 模式**：`app_config.docker.json` 默认 `submit_mode: guarded`，不会真实下单
- **切换 live**：修改 `submit_mode` 为 `live` + `live_submit: true`（需先生确认）
- **运行时日志**：持久化在 `runtime/engine/`，跨容器周期保留
- **时区**：容器内设为 `Asia/Shanghai`
- **容器以 root 运行**：为简化 volume mount 权限，容器内以 root 运行（本地开发工具，非生产暴露）

### 7. 常见操作

```bash
# 查看最近日志
cat runtime/engine/logs/cycles.jsonl | tail -5

# 查看执行状态
cat runtime/engine/state/execution_state.json

# 手动解锁（如果系统被锁定）
cat runtime/engine/state/control_state.json
# 编辑后重新写入

# 重建镜像（依赖更新后）
docker compose build --no-cache
```
