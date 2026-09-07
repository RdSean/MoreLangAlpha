# Docker Compose 部署入口

部署 Compose 文件统一放在本目录。根目录的 `docker-compose.yml` 保持兼容旧命令，不作为新分层部署的唯一入口。

## 配置边界

复制 `deploy/.env.example` 为 `deploy/.env`，填写 PostgreSQL、Redis 和 MinIO 的启动参数：

```bash
cp deploy/.env.example deploy/.env
```

`deploy/.env` 只供 middleware Compose 插值，不会传给后端。根目录 `.env` 仍用于直接启动 Python 后端及其数据库、Redis、S3 客户端连接；当后端连接本地 middleware 时，两份文件中的数据库用户名、密码、库名和 Redis 密码必须一致。

默认数据目录均位于本目录下，且不会提交到 Git：

```text
deploy/volumes/postgresql
deploy/volumes/redis
deploy/volumes/minio
```

在 `deploy/.env` 设置 `POSTGRES_DATA_DIR`、`REDIS_DATA_DIR` 或 `MINIO_DATA_DIR` 后，可将对应数据迁移到任意绝对路径，例如 NAS 挂载点。

## 中间件

启动 PostgreSQL、Redis、MinIO 和教育附件桶初始化任务：

```bash
docker compose --env-file deploy/.env \
  -f deploy/docker-compose-middleware.yml up -d
```

默认会使用 `deploy/volumes/*`。`docker-compose-local.yml` 保留为空的兼容入口，
不会覆盖这些默认路径；需要外部路径时，请直接在 `deploy/.env` 设置对应的
`*_DATA_DIR` 变量，或使用 NAS override。

## 开发服务

中间件启动后，在另一个终端启动后端和前端：

```bash
docker compose --env-file deploy/.env \
  -f deploy/docker-compose-middleware.yml \
  -f deploy/docker-compose-dev.yml \
  up -d --build
```

开发服务通过名为 `langalpha-middleware` 的 Docker 网络访问 `postgres`、`redis` 和 `minio`。

## NAS

复制 `docker-compose-nas.example.yml` 为本地的 `docker-compose-nas.yml`，将三个路径改为 NAS 上的实际目录，然后叠加该文件：

```bash
docker compose --env-file deploy/.env \
  -f deploy/docker-compose-middleware.yml \
  -f deploy/docker-compose-nas.yml up -d
```

PostgreSQL、Redis 和 MinIO 都使用 bind mount；备份或迁移时，停止对应服务后复制其目录即可。
