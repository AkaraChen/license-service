# Kamal 本机端到端验证

验证日期：2026-09-07。结果：首次部署和第二次更新部署均成功。
本次运行了真正的 `kamal setup` / `kamal deploy`，不只是解析配置。

## 测试环境

- 本机临时 `docker:29-dind` 容器模拟 Linux 服务器，安装 SSH 服务，使用一次性 SSH 密钥。
- 官方 `ghcr.io/basecamp/kamal:v2.12.0` CLI 通过 SSH 管理该服务器的嵌套 Docker。
- 临时 `registry:2` 接收构建后的应用镜像，不使用真实 GHCR 凭据。
- 模拟服务器内运行 Caddy、kamal-proxy、Redis 和 License Service。
- HTTPS 链路：浏览器 → Caddy → kamal-proxy → Gunicorn/Django → SQLite / Redis。
- 使用当前工作区的独立 Git 副本测试，包括尚未提交的 Kamal 配置；没有修改当前分支或推送测试版本。

模拟服务器需要 privileged 才能运行嵌套 Docker；没有挂载宿主机 Docker socket 或业务数据。
这是测试基础设施的权限，不是生产应用容器的权限要求。

## 与生产配置的差异

1. 服务器和域名换为本地测试地址；部署目标不是公网服务器。
2. GHCR 换为 Docker 网络内部的临时 HTTP registry；测试 Docker daemon 仅对该 registry 配置 insecure-registry。
3. `builder.driver` 使用 `docker`，构建操作也在本机模拟服务器的 Docker daemon 上进行。
4. Caddy 使用 `tls internal`，通过一个测试 accessory 启动，暴露的 HTTPS 端口最终只绑定宿主机回环地址。
5. Caddy 终止 TLS，因此本次覆盖配置使用 `proxy.ssl: false` 和 `proxy.forward_headers: true`。
   仓库生产配置仍使用 kamal-proxy 直接终止 TLS，保留 `ssl: true`、`forward_headers: false`。

使用 curl 加载 Caddy 根证书，验证了 HTTPS 证书链；浏览器使用忽略本地 CA 错误的独立测试会话。
没有测试公网 DNS、Let's Encrypt 自动签发、真实 GHCR 认证或云服务器防火墙。

## 结果

| 检查 | 结果 |
| --- | --- |
| `kamal setup` | 成功，约 65 秒；SSH、构建、推送/拉取、代理/accessory 启动、数据库迁移及就绪切换完成 |
| Docker 健康状态 | 应用与 Redis 均为 healthy |
| HTTPS `/healthz` | 返回 200，`{"status":"ok"}` |
| 浏览器注册 | 成功创建账号并进入“我的授权”页面 |
| 退出后重新登录 | 成功 |
| Kamal 管理命令 | `app exec --reuse` 调用 `createsuperuser` 成功 |
| 管理员浏览器登录 | 成功进入 `/admin/`，静态样式正常 |
| 浏览器运行错误 | 用户及管理员测试会话均未报告 JavaScript 异常 |
| HTTPS 安全设置 | 登录响应包含 Secure Cookie 和 HSTS |
| 第二次 `kamal deploy` | 成功，约 51 秒，生成新版本并替换旧容器 |
| 切换期间连续探测 | 51 次 HTTPS 健康请求全部返回 200；这是采样结果，不代表完整的零中断保证 |
| 更新后数据与会话 | 原账号仍存在，原浏览器会话刷新后仍保持登录 |
| 实际应用权限 | UID/GID 10001、只读根目录、cap-drop ALL、no-new-privileges、pids-limit 64 |

一次运行中的内存快照：应用约 83 MiB、Redis 约 3.9 MiB、Caddy 约 13.5 MiB、
kamal-proxy 约 3.4 MiB。该快照不包含宿主机系统、Docker daemon 和镜像构建开销，也不是负载容量测试。

## 证据与清理

本机详细日志、测试配置副本、证书及页面截图保存在 `/tmp/license-kamal-e2e/`，包括：

- `setup.log`：首次部署日志。
- `redeploy.log`、`redeploy-result.json`：更新部署及连续探测结果。
- `customer.png`、`admin.png`：真实浏览器页面截图。
- `repo/config/deploy.yml`、`repo/config/Caddyfile.test`：本地测试覆盖配置。

临时浏览器、SSH 模拟服务器、registry、测试网络及容器匿名数据卷已清理。
日志含临时测试账号信息，不应公开上传。生产部署按 [Kamal 部署指南](kamal.md) 操作。
