# 数据库

账号、密钥、授权、设备和登录会话存在数据库里。登录限流的计数存在 Redis。两边都要备份，停服务时不要把数据卷删掉。

## 默认：SQLite

容器把数据放在 Docker 数据卷上。Docker Compose 用 `license-data` 和 `redis-data`，Kamal 用 `license-service-data` 和 `license-service-redis-data`。名字不同，不会自动迁移，也不要混用。

SQLite 只给一台机器用。不要让多个应用实例同时写同一个文件。写入量大了再换 PostgreSQL。

升级前把数据卷复制出来，或把库文件拷走。停止服务时不要删除数据卷。

## PostgreSQL

把连接写进 `LICENSE_DATABASE_URL`：

```bash
LICENSE_DATABASE_URL=postgresql://user:password@host:5432/licenses
```

默认是 SQLite。改用 PostgreSQL 要把数据迁过去。新建的空库读不到原来的 SQLite 文件。

## Redis

Docker Compose 和 Kamal 都会在同一台机器上起 Redis。和数据库一起备份。两套互不相干的部署不要共用同一个 Redis。

## 升级

新进程启动时会自动做数据库迁移。把应用换回旧版，数据库不会跟着回滚。
