# Config Layers

`config/` 现在采用分层配置：

- `app.defaults.json`：项目默认值，进 git
- `app_config.docker.json`：Docker/容器环境覆盖，进 git
- `user.settings.json`：本地用户设置，不进 git
- `user.settings.example.json`：本地用户设置样板，进 git

## Global Broker Platform

全局券商平台配置统一放在：

- `broker.platform`

当前默认值：

- `tiger`

Dashboard 的 `/api/config` 会读取和写回这个字段，`/api/broker` 会返回当前生效平台与可选平台列表。  
如果需要本地覆盖，可以通过 `config/user.settings.json` 修改该字段。

有效配置的合并顺序：

`app.defaults.json <- app_config.docker.json <- user.settings.json`

敏感值如 `telegram_target` 建议通过环境变量占位符注入，例如：

- `${ENGINE_TELEGRAM_TARGET}`

主 agent 的真实会话标识也建议通过环境变量传入：

- `${ENGINE_MAIN_AGENT_SESSION_KEY}`

当前 Docker 运行入口仍保持为：

- `config/app_config.docker.json`

## 兼容与退役

- 保留：
  - `config/app.defaults.json`
  - `config/app_config.docker.json`
  - `config/user.settings.example.json`
- 退役为兼容参考：
  - `system/engine/app_config.paper.json`
  - `system/engine/config.example.json`
