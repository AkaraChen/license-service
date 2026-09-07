# Docker

生产用仓库里的 `compose.production.yaml`。需要 Docker Compose 2。

先准备 `.env`：复制 `.env.example`，生成一次会话密钥，填进 `LICENSE_SESSION_SECRET`，再填实际域名 `LICENSE_ALLOWED_HOSTS`。

```bash
cp .env.example .env
python3 -c 'import secrets; print(secrets.token_urlsafe(48))'
docker compose -f compose.production.yaml up -d --build
docker compose -f compose.production.yaml exec app python manage.py createsuperuser
```

应用只听本机的 `8000` 端口，前面接你自己的代理，不要把这个端口暴露到外面。代理不在这份文件里。如果代理也跑在容器里，加入同一网络，转到 `app:8000`。

## 镜像

已发布的镜像在 `ghcr.io/shukka-app/shukka-license`，目前只有 64 位 x86。生产环境按完整提交号拉取，不要用 `latest`。

本机构建，或拉取已发布的某一版：

```bash
docker build -t shukka-license:local .
docker pull ghcr.io/shukka-app/shukka-license:<完整提交号>
```

看日志、停服务（保留数据卷）：

```bash
docker compose -f compose.production.yaml logs --tail=100 app
docker compose -f compose.production.yaml down
```

数据卷说明见 [数据库](database.md)。
