# Config Layers

`config/` 现在采用分层配置：

- `app.defaults.json`：项目默认值，进 git
- `app_config.docker.json`：Docker/容器环境覆盖，进 git
- `user.settings.json`：本地用户设置，不进 git
- `user.settings.example.json`：本地用户设置样板，进 git

有效配置的合并顺序：

`app.defaults.json <- app_config.docker.json <- user.settings.json`

敏感值如 `telegram_target` 建议通过环境变量占位符注入，例如：

- `${ENGINE_TELEGRAM_TARGET}`

当前 Docker 运行入口仍保持为：

- `config/app_config.docker.json`
