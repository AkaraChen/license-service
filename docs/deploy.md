# 部署概览

服务本体是一个 Python 项目。账号、密钥和设备绑定在数据库里；登录限流在 Redis。这两处都要在，服务才能用。

## 选哪条路径

| 方式 | 适合 |
| --- | --- |
| [Docker Compose](docker.md) | 机器上已经有自己的部署方式 |
| [Kamal](kamal.md) | 一台 Linux 服务器，从安装到发布都交给部署工具 |

两条路径用同一份镜像。Compose 和 Kamal 的数据卷不是同一套，选好之后不要混着搬，数据不会自己过去。

默认按一台机器跑。不要把同一份数据库挂到多台机器上，也不要给 Kamal 加第二台应用主机。写入量大了再换 [PostgreSQL](database.md)。

## 必要配置

生产必须有一份会话密钥，以及这台服务对外使用的主机名。改过配置要重启。没有密钥或数据库连不上，进程起不来。

会话密钥生成一次，填进 `LICENSE_SESSION_SECRET`，以后部署继续用这一份：

```bash
python3 -c 'import secrets; print(secrets.token_urlsafe(48))'
```

其余常见项：

| 变量 | 说明 |
| --- | --- |
| `LICENSE_ALLOWED_HOSTS` | 逗号分隔的域名或主机名 |
| `LICENSE_DATABASE_URL` | 不填则用 SQLite，见 [数据库](database.md) |
| `LICENSE_REDIS_URL` | Redis 地址，例如 `redis://redis:6379/0` |
| `LICENSE_TRUST_PROXY` | 前面有会改写协议头的代理时设为 `1` |
| `WEB_CONCURRENCY` | 同时处理请求的进程数，默认 `1`；调大时提高内存上限 |

## 第一个管理员

管理员不能在网页上自行开通，只能用命令创建。

```bash
# Compose
docker compose -f compose.production.yaml exec app python manage.py createsuperuser

# Kamal
kamal superuser
```

创建完成后打开管理后台即可登录。

## 更新

先按 [数据库](database.md) 把数据拷出来，再换新版本。新进程启动时会自动做数据库迁移。把镜像换回旧版，数据库不会跟着回滚。

Docker Compose 在同一份 `compose.production.yaml` 上重建并拉起：

```bash
docker compose -f compose.production.yaml up -d --build
```

若用已经发布的镜像，先拉到你钉住的那一版，再 `up -d`，不要加 `-v`。

Kamal 先把要发布的代码提交，再执行：

```bash
kamal deploy
```

用已经发布的镜像时：

```bash
kamal deploy --skip-push --version <这一版的完整提交号>
```

具体步骤分别见 [Docker](docker.md) 和 [Kamal](kamal.md)。
