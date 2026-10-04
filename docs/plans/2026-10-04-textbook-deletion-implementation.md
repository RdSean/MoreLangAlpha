# Textbook Deletion Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 家长可不可恢复删除所属家庭教材，保留图书馆来源。

**Architecture:** 教育模块事务删除关联记录，持久清理队列处理教材专属对象。沿用教育任务扫描和现有权限、查询及Dialog组件，不修改PTC执行机制。

**Tech Stack:** FastAPI、async psycopg、Alembic SQL、React Query、React、Vitest。

---

### Task 1: 删除事务与持久清理

Files: 新增 migrations/versions/083_textbook_deletion_cleanup.py、src/server/database/education_book_deletion.py、src/server/services/education_book_deletion.py；修改教育服务与路由、education_book_jobs.py扫描；测试 tests/integration/test_education_books_db.py、tests/unit/server/services/test_education_book_deletion.py。

先加入缺失删除函数、权限与清理失败重试测试，运行观察失败。新增事务：锁定所属教材、锁任务和学习线程，阻止 queued/running 项及 in_progress runtime；删除 learning_spaces 和学生学习线程、materials、jobs，清空 current_structure_id 后删除教材，登记精确前缀清理记录。存储清理严格枚举，仅处理验证后的前缀；任一删除失败不移除队列。扫描复用现有服务，不增加模块级运行状态。

Run: uv run pytest tests/unit/server/services/test_education_book_deletion.py -q；uv run pytest tests/integration/test_education_books_db.py -k deletion -q。预期从缺失功能失败转为通过，并验证图书馆记录未修改。检查迁移目标后升级开发库，不对开发库运行集成测试的schema重置。

### Task 2: 家长列表删除交互

Files: web/src/pages/Education/TextbooksPage.tsx、api.ts、queries.ts、__tests__/TextbooksPage.test.tsx。

先增加学生无入口、取消不调用、确认正确教材、失败保持对话框、活跃任务禁止的测试并观察失败。加入Trash2图标和Tooltip，Dialog展示不可恢复范围，mutation成功后清除教材相关缓存并刷新教材、来源和学生授权列表；失败展示服务错误，不误报成功。

Run: cd web && pnpm exec vitest run src/pages/Education/__tests__/TextbooksPage.test.tsx。再执行相关API/query测试及pnpm build。

### Task 3: 验证与收口

运行后端聚焦回归、Ruff、前端测试/build和git diff --check。检查5177/8000及LAN可用性，浏览器确认列表和确认框桌面/手机布局。真实删除只针对验收数据且动作前确认。更新中文CHANGELOG与本计划验收记录，原子提交，不纳入用户业务活动文档/PDF或本地配置。

## 验收记录（2026-10-04）

- Task 1、2、3已实施。开发库升级083；集成测试仅使用langalpha_test。
- 后端聚焦99 passed；完整教材集成文件17 passed；教育前端16文件117 passed；pnpm build、Ruff和改动ESLint通过。
- 独立复核发现上传锁占应用池槽位引发嵌套借用饥饿，已改为独立短生命周期连接，新增不借应用池回归；外部IO不持数据库事务。
- 浏览器验证家长列表、桌面/375px确认框及取消；手机document宽度与scrollWidth均375px。未点击永久删除现有用户教材。删除和来源保留的实际数据库行为通过专用集成数据验证。
- 前端0.0.0.0:5177可从当前LAN地址访问，后端8000启动。对象清理在事务提交后由持久队列重试；共享PTC账本、checkpoint和学生Flash工作区保留，不声称运行数据的取证级擦除。
