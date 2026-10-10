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

按用户确认，本机 Docker MinIO 使用当前 worktree `.env` 中后端已在使用的 STORAGE_* 配置；不输出、复制或提交凭据。

## 当前执行状态

- 25 项卡牌单元测试、3 项分层检查通过；此前 5 项 PostgreSQL 集成测试与迁移往返检查通过，Ruff 通过。
- 本机 Docker MinIO S3 地址为 `http://127.0.0.1:9000`，桶为 `onemore-education`，使用后端现有 `.env` 配置。
- 已完成实际导入：191 张卡图，总计 174,926,986 字节；逐张下载校验全部通过，191 条卡牌元数据与 CSV 全字段一致。
- 开发数据库升级至 091；原有作业 204、规则 13、家庭日历 1，升级前后数量一致。
- 修复本机 MinIO 将校验值元数据名称返回为 `Sha256` 时的兼容问题，按大小写无关的名称核验，并拒绝冲突的重复字段；已有完整对象直接复用。
- 再次执行导入：uploaded_images = 0、existing_images = 191、changed_records = 0；卡牌 ID 和更新时间指纹保持一致。

后续重新导入可运行以下命令：

```bash
uv run python scripts/ops/import_pokemon_cards.py \
  --csv '/Users/seanlee/DevelopCode/MoreAlpha/官方图片/卡牌数据库_官方数据.csv' \
  --image-root '/Users/seanlee/DevelopCode/MoreAlpha/官方图片' \
  --apply --verify
```

凭据不放入命令行参数、文档或仓库；图片验证成功前不单独导入元数据。
