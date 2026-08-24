# Docker Compose 部署入口

部署 Compose 文件统一放在本目录。根目录的 `docker-compose.yml` 保持兼容旧命令，不作为新分层部署的唯一入口。

## 中间件

启动 PostgreSQL、Redis、MinIO 和教育附件桶初始化任务：

```bash
docker compose --env-file .env \
  -f deploy/docker-compose-middleware.yml \
  -f deploy/docker-compose-local.yml up -d
```

本机 MinIO 数据挂载到 `/Users/seanlee/Downloads/LangOneMore`。此路径只在 `docker-compose-local.yml` 中定义，不进入后端 `.env`。

## 开发服务

中间件启动后，在另一个终端启动后端和前端：

```bash
docker compose --env-file .env \
  -f deploy/docker-compose-middleware.yml \
  -f deploy/docker-compose-dev.yml \
  -f deploy/docker-compose-local.yml up -d --build
```

开发服务通过名为 `langalpha-middleware` 的 Docker 网络访问 `postgres`、`redis` 和 `minio`。

## NAS

复制 `docker-compose-nas.example.yml`，将 `/mnt/tank/langalpha/minio` 改为 NAS 上的实际目录，然后用它替换 local 文件：

```bash
docker compose --env-file .env \
  -f deploy/docker-compose-middleware.yml \
  -f deploy/docker-compose-nas.yml up -d
```

数据库和 Redis 的 named volume 仍由 middleware Compose 文件管理；MinIO 使用 local/NAS override 明确指定持久化目录。
