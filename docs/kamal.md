# 用 Kamal 单机部署

仓库已提供 `config/deploy.yml`，不需要另建 Rails 项目，也不用运行 `kamal init`。
运行架构是一台服务器上的应用、Redis 和 kamal-proxy；SQLite 保存在 Docker 数据卷。
使用现有 Dockerfile 在部署操作者的电脑上构建，只构建一个 CPU 架构，服务器无需编译资源。
Kamal 自动处理 HTTPS，配置方式参考 [Kamal 安装文档](https://kamal-deploy.org/docs/installation/)
和 [代理文档](https://kamal-deploy.org/docs/configuration/proxy/)。

## 准备

- 一台可以用 SSH 密钥登录的 Linux 服务器；默认使用 `root` 安装和管理 Docker。
  SSH 管理权限与容器用户不同：应用仍以 UID/GID `10001` 运行。
- 一个域名，DNS 直接指向这台服务器。开放 80/443；SSH 端口只向管理员开放。
  此最小配置由 kamal-proxy 直接终止 TLS，不在前面叠加其他 CDN/代理。
- 操作者电脑安装 Docker（含 Buildx）、Git 和 Ruby；服务器不需要 Ruby。
- 一个 GitHub 容器镜像命名空间，以及有该命名空间镜像读写权限的 GHCR token。
  Token 按当前 GitHub Packages 要求创建，参见
  [GHCR 身份验证](https://docs.github.com/en/packages/working-with-a-github-packages-registry/working-with-the-container-registry#authenticating-with-a-personal-access-token-classic)。

```bash
gem install kamal -v 2.12.0
cp .kamal/secrets.example .kamal/secrets
chmod 600 .kamal/secrets
python3 -c 'import secrets; print(secrets.token_urlsafe(48))'
```

把 token 和生成的固定密钥填入 `.kamal/secrets`。这个文件已被 Git 忽略，也不会进入镜像。
不要每次部署重新生成会话密钥。Kamal 使用自己的 secrets 文件，不自动复用 Compose 的 `.env`。

编辑 `config/deploy.yml` 中的四个值：

| 配置 | 填写内容 |
| --- | --- |
| `x-server` | 服务器公网 IP |
| `x-domain` | 实际域名 |
| `x-registry-user` | GitHub 登录名 |
| `image` | 小写的 `用户名或组织名/license-service`，不含 `ghcr.io/` 前缀 |

默认 `builder.arch: amd64`。如果服务器是 ARM64，改为 `arm64`；本地 Docker 需要能构建对应架构。
如果 SSH 用户不是 root，可增加 `ssh.user`，并提前安装 Docker、配置该用户的 Docker 管理权限。

## 首次部署及更新

先提交应用代码和部署配置。Kamal 默认按 Git 提交构建，未提交的代码不会进入镜像。
密钥文件不要提交。

```bash
kamal config                    # 本地检查；输出可能包含敏感配置，不要分享
kamal setup                     # 安装 Docker、启动 Redis/代理、构建推送并部署应用
kamal superuser                 # 在正在运行的容器内交互式创建管理员
```

访问 `https://你的域名/ui/login` 或 `/admin/`。
后续代码更新、提交后执行 `kamal deploy`；查看日志使用 `kamal logs`。
Redis accessory 独立管理，普通 `kamal deploy` 不会更新它，参见
[Accessories 文档](https://kamal-deploy.org/docs/configuration/accessories/)。

## 资源、权限与数据

- 应用上限 256 MiB、1 CPU，默认一个 worker；Redis 上限 96 MiB、0.25 CPU，数据上限 32 MiB。
  部署切换时新旧应用会短暂并存，服务器还需要给系统、Docker 和代理留出内存，不能把单容器上限当作整机需求。
- 应用保持只读根文件系统、普通用户、移除 capabilities 和禁止提权；仅 `/data`、`/tmp` 可写。
  Redis 沿用官方入口脚本，先调整数据目录权限，再降权运行。两个容器都限制最多 64 个进程/线程。
- 应用和 Redis 不发布宿主机端口，通过 Kamal 内部网络通信；不要在同一网络放置不可信服务。
  `forward_headers: false` 让代理依据实际连接生成协议头，不信任客户端自带的转发头。
- Kamal 通过 `/healthz` 确认数据库和 Redis 就绪后才切换流量。`config.kamal` 仅让此固定健康响应
  绕过 Host 校验，兼容代理以容器 ID 发起的探测；业务路由仍严格校验域名。
  Docker 也持续执行轻量探针。unhealthy 状态不会自行触发容器重启。
- 数据分别在 `license-service-data` 和 `license-service-redis-data` 卷中。本配置与 Compose 使用不同的卷，
  不会自动搬迁原有数据。切换已有部署前，需要先停写并迁移数据。
- 仅部署到一台服务器。SQLite 不跨服务器共享，不能直接给 `servers.web.hosts` 添加第二台机器。
  升级前备份数据库；启动时自动迁移，新旧版本重叠期间要求迁移向后兼容。破坏性迁移应安排维护停机，
  回滚应用镜像不会自动回滚数据库。
- 保留最近两个应用容器，限制历史镜像占用；仍需监控磁盘和备份，避免执行删除数据卷的清理命令。

## 已验证的本机流程

已在带 SSH 的本机嵌套 Docker 服务器上实际运行 `kamal setup` 和第二次 `kamal deploy`，
并通过 Caddy HTTPS 验证注册、登录、管理员后台及数据/会话保留。
测试环境与公网部署的差异见 [本机端到端验证记录](kamal-local-validation.md)。
