# Kamal

给一台 Linux 服务器用。填好服务器、域名和镜像仓库之后，Kamal 会安装 Docker、拉起应用和 Redis、对外接流量。只部署一台机器。数据在卷里，和 Docker Compose 不是同一套，见 [数据库](database.md)。

仓库里已经有 `config/deploy.yml`。安装说明见 [Kamal](https://kamal-deploy.org/docs/installation/)。

## 准备

- 能用 SSH 密钥登录的 Linux 服务器（默认用 `root` 安装并管理 Docker）
- 域名指到这台机器，并开放 80、443 端口
- 你自己的电脑上有 Docker、Git 和 Ruby；服务器不需要 Ruby
- 目标镜像仓库的读写凭据

```bash
gem install kamal -v 2.12.0
cp .kamal/secrets.example .kamal/secrets
chmod 600 .kamal/secrets
```

会话密钥生成一次，把输出和仓库凭据一起写入 `.kamal/secrets`：

```bash
python3 -c 'import secrets; print(secrets.token_urlsafe(48))'
```

这个文件已被 Git 忽略。Kamal 不会去读 Docker Compose 用的 `.env`。

编辑 `config/deploy.yml` 里这四项：

| 配置 | 填写 |
| --- | --- |
| `x-server` | 服务器公网 IP |
| `x-domain` | 实际域名 |
| `x-registry-user` | GitHub 用户名 |
| `image` | 小写 `用户或组织/shukka-license`，不要加 `ghcr.io/` 前缀 |

默认镜像是 `shukka-app/shukka-license`。配置里的服务名和卷名保持旧名字，已经在跑的安装可以继续用原来的数据。

默认按 64 位 x86 构建（配置项是 `amd64`）。服务器是 ARM 就改成 `arm64`，并确保你自己的 Docker 能构建这个架构。SSH 用户不是 root 时，先装好 Docker，再设置 `ssh.user`。

## 第一次

先提交要发布的代码。未提交的内容不会进镜像。不要提交密钥文件。

```bash
kamal config
kamal setup
kamal superuser
```

`kamal config` 用来在本机检查配置，输出里可能有密钥，不要外传。`kamal setup` 会在服务器上装 Docker、拉起 Redis 和代理、构建并发布应用。`kamal superuser` 创建第一个管理员。

之后改代码、提交，再执行 `kamal deploy`。看日志用 `kamal logs`。Redis 不会跟着普通的 `kamal deploy` 更新。

## 用已经发布的镜像

不想在本机构建时，直接用已经发布的镜像。仓库地址是 `ghcr.io`，凭据只要有拉取权限。目前发布的是 64 位 x86。

```bash
kamal setup --skip-push --version <这一版的完整提交号>
kamal deploy --skip-push --version <这一版的完整提交号>
```

不要执行会删除数据卷的清理。不要加第二台应用主机。
