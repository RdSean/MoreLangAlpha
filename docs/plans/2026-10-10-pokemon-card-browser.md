# Pokemon Card Browser Implementation Plan

**Goal:** 在 Settings 的二级页面分页查看已导入的宝可梦卡牌。

**Architecture:** 家庭账户设置提供入口，独立懒加载 `/settings/pokemon-cards`。家长身份读取全局卡牌目录；数据库提供稳定分页，服务校验权限和存储对象，后端代理图片，避免把 localhost MinIO 地址暴露给局域网设备。沿用已有表结构，无须新增迁移。

**Tech Stack:** FastAPI、async psycopg、现有 S3 streaming helper、React Query、Radix Dialog、主题 tokens。

## 范围与交互

- 每页 20 张，桌面 4 列、宽屏 5 列，平板 3 列、手机 2 列。
- 顶部返回家庭账户、卡牌总数和系列筛选；底部上一页/下一页和页码选择。
- 图片保持完整比例，卡片显示名称、系列、卡号。点击查看大图和详细属性。
- 请求和图片支持加载、失败重试及空目录状态。
- 仅家长可浏览，后续学生奖励/兑换/收藏体系另行实现；主菜单不增加入口。

## Task 1: 只读目录和图片 API

1. 在 `tests/unit/server/services/test_education_pokemon_catalog.py` 添加权限、对象边界、流关闭和异常测试，观察缺失功能导致的失败。
2. 扩展 `src/server/database/education_pokemon_cards.py`：系列列表、总数、分页和按 UUID 读取；按系列、数字编号、source ID 稳定排序。
3. 新建 `src/server/services/education_pokemon_catalog.py` 和 `src/server/app/education/pokemon_cards.py`，在 `src/server/app/setup.py` 注册。API 不返回 bucket/key，图片通过认证后代理，并支持 ETag 重新校验。
4. 在现有 PostgreSQL 集成测试覆盖数字顺序、筛选、分页边界、空集合和对象读取；路由测试覆盖参数和状态码。

## Task 2: Settings 二级页面

1. 新建 `web/src/pages/Settings/PokemonCardsPage.tsx`、本地 API/query 模块及 CSS；增加集中 query key。
2. 修改 `FamilyAccountsTab.tsx` 添加入口；修改 `Main.tsx` 和 `routeChunks.ts` 增加独立路由及预加载。
3. Testing Library 验证分页、筛选重置、权限、大图、失败重试；Playwright 验证响应式列数、完整卡图和返回设置。

## Task 3: 验证与交付

1. 运行聚焦 pytest、PostgreSQL 集成测试、相关 Settings/Education Vitest、前端 build、修改文件 lint。
2. 通过 Playwright 检查手机与桌面、Quiet/NASA 主题；使用真实后端和已导入图片验证局域网访问。
3. 更新中文 `CHANGELOG.md`，仅提交本功能文件，保留无关工作区变更。
