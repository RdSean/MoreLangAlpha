# 宝可梦卡牌目录导入

## 范围

用户已授权导入「官方图片」中的 CSV 和对应 PNG，用于后续作业积分奖励。
本次建立共享内容目录，不实现奖励、兑换、学生收藏或成就界面。
现有家庭作业、Flash、PTC 和 Docker 配置不变。

## 数据与存储

- 实际输入：191 条唯一卡牌 ID、191 张 PNG，两个系列，无缺图。
- 新增 Alembic `091_pokemon_cards`，衔接 `090_household_calendars`。
- `education_pokemon_cards` 保存稳定内部 UUID、来源 ID、系列代码/名称、卡名、类别、属性、可空 HP、阶段、卡号、稀有度、画师、备注和原图片相对路径。
- 图片字段保存 bucket、对象 key、MIME、SHA-256、字节数及尺寸；不保存临时签名 URL。
- 图片 key 固定在 `education/pokemon/cards/<source-id>/<sha256>.png`。只操作确定的卡牌 key，不列举、覆盖或删除其他对象。
- 内容改变生成新 key；相同来源 ID 更新原记录并保留内部 UUID，相同数据重复导入不更新时间戳。

## 实施与验证

1. 解析 BOM CSV，校验字段、重复 ID、相对路径、图片完整性及校验值；默认 dry-run，无远端写入。
2. 实现条件上传、已存在对象校验和有界并发；全部图片成功后事务批量 upsert 元数据。
3. 增加解析、对象冲突、失败重试与真实 PostgreSQL 测试；仅测试库执行升级/回滚/再升级并检查既有表数据。
4. 升级开发数据库至 091，执行已授权实际导入；下载核验全部卡图并再次导入确认无重复。
5. 更新中文 CHANGELOG，独立提交代码与迁移，不提交原始图片、CSV、凭据或生成文件。

MinIO 凭据仅由本地密码文件读取到运行进程，导入工具使用现有 STORAGE_* 配置，不记录凭据。

## 当前执行状态

- 23 项卡牌单元测试、3 项分层检查和 5 项 PostgreSQL 集成测试通过；Ruff 通过。
- 实际 CSV dry-run 验证 191 张卡图，总计 174,926,986 字节。
- 开发数据库升级至 091；原有作业 204、规则 13、家庭日历 1，升级前后数量一致。
- 实际上传被环境连接信息阻塞：指定 LAN 9000 返回 ZLMediaKit，本机 MinIO 对密码文件中的访问 ID 返回 InvalidAccessKeyId。没有写入卡牌元数据或上传图片。
- 获取正确 MinIO S3 地址后，从本地密码文件将凭据读入进程环境，运行下列命令，接着重复运行检查 uploaded_images/changed_records 均为 0：

```bash
uv run python scripts/ops/import_pokemon_cards.py \
  --csv '/Users/seanlee/DevelopCode/MoreAlpha/官方图片/卡牌数据库_官方数据.csv' \
  --image-root '/Users/seanlee/DevelopCode/MoreAlpha/官方图片' \
  --apply --verify
```

凭据不放入命令行参数、文档或仓库；图片验证成功前不单独导入元数据。
