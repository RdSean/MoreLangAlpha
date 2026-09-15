# 文档图片落盘 — 实施计划

**Goal:** 让 Datalab 提取的图片作为 artifact 落到对象存储，并让文档预览能真正显示
它们（相对引用在渲染时解析）。

**Design:** `docs/plans/2026-09-15-document-image-artifacts-design.md`（D1–D7）。

**分支：** `feature/platform-core-migration`,
`/Users/seanlee/.config/superpowers/worktrees/langalpha/platform-core-migration`

**每个任务的规矩**（与上一份计划一致）：

* 一个任务一个提交，提交信息里带验证输出。
* 同一个提交里更新 `CHANGELOG.md`（中文）。
* 测试必须先看到失败；实现后补的测试要做变异验证并在提交信息里说明。
* 后端 `uv run pytest tests/unit -q -p no:randomly`、`uv run ruff check src/ migrations/`；
  前端 `pnpm vitest run`、`pnpm typecheck`、`pnpm lint`、`pnpm build`。
* 金额一律整数分；不引入浮点。

---

## Task 1：部署配置（图片上限）

**Files:** `src/config/env.py`、`src/config/settings.py`、
`tests/unit/config/test_document_image_limits.py`

1. 新 env：`DOCUMENT_MAX_IMAGE_ARTIFACTS`（默认 200）、
   `DOCUMENT_MAX_IMAGE_BYTES`（默认 32 MiB），沿用 `_positive_int`。
2. `DocumentParsingConfig` 增加两个字段并在 `get_document_parsing_config()` 里透传。
3. 测试：默认值、从 env 覆盖、非正数报错。

## Task 2：provider 落盘图片

**Files:** `src/server/documents/providers/datalab.py`、
`tests/unit/server/documents/providers/test_datalab_images.py`

1. 先写失败测试：
   * `result.images = {"a_img.jpg": base64}` → bundle 里多出一个
     `embedded_image` artifact，`relative_path == "a_img.jpg"`，文件内容 = 解码后的
     字节，`media_type` 按魔数判定（JPEG/PNG）。
   * 主 artifact（markdown）的 metadata 里带
     `images_kept` / `images_dropped` / `image_bytes`。
   * 文件名带路径（`../x.jpg`、`a/b.jpg`）→ 只取 basename；重复名 → 去重不覆盖。
   * 超过数量或总字节上限 → 丢弃并在 metadata + `warning` 里记账（被引用优先）。
   * `disable_image_extraction=True`（或没图）→ 行为与今天完全一致（1 个 artifact）。
2. 实现：`_write_images()`，魔数判定，basename 清洗，去重，上限裁剪。
3. 验证：`tests/unit/server/documents/providers/` 全绿。

## Task 3：执行器区分图片预算

**Files:** `src/server/documents/executor.py`、`tests/unit/server/documents/test_executor.py`

1. 失败测试：
   * 图片字节**不计入** `max_bundle_bytes`（构造 markdown 小 + 图片超
     `max_bundle_bytes` 但低于 `max_image_bytes` 的 bundle → 成功）；
   * 图片总字节超过 `max_image_bytes` → `invalid_parser_output`，消息可区分；
   * 普通 artifact 超 `max_bundle_bytes` 仍然失败（回归）。
2. 实现：`_validate_bundle` 按 kind 分账；新增构造参数 `max_image_bytes`（默认取配
   置），并加 `max_artifacts` 触发条件的说明。

## Task 4：前端渲染时解析相对引用

**Files:** `web/src/pages/Documents/artifactImages.ts`（新）、
`web/src/pages/Documents/components/DocumentPreviewDrawer.tsx`、
`web/src/pages/Documents/__tests__/artifactImages.test.ts`、
`web/src/pages/Documents/__tests__/DocumentPreviewDrawer.images.test.tsx`

1. 失败测试：纯函数 `resolveRelativeImageSources(markdown, artifacts, origin)`
   * 命中 `relative_path` → 绝对 URL；用 basename 也能命中（`images/a.jpg` 引用对
     `a.jpg`）；
   * 外部 URL / `data:` / `blob:` 不动；未命中不动；非图片 artifact 不参与；
   * `![alt](a.jpg "title")` 的 title 保留。
2. `DocumentPreviewDrawer` 在渲染 markdown 前调用它（`useMemo`，依赖 artifacts）。
3. 验证：`pnpm vitest run src/pages/Documents`。

## Task 5：默认值翻转与文案

**Files:** `src/server/documents/providers/datalab_options.py`、
`web/src/pages/Documents/components/DatalabOptionsFields.tsx`、
`web/src/locales/{zh-CN,en-US}.json`、相关测试

1. `disable_image_extraction` 默认 `False`（并更新其 docstring：理由已消失）。
2. 向导复选框默认勾选；提示文案改成"图片会另存为独立文件并在预览中显示"，中英
   双语同步；`disable_image_captions` 保持默认 `True`。
3. 测试：默认态与"只在改动时发送"的既有契约不回归。

## Task 6：真实链路端到端

1. 用 `RE3 Part.pdf` 走完整 API：上传 → 检测 → 选中 datalab-online（开图片）→
   解析 → 断言 artifact 列表里 markdown 1 个 + 图片 N 个、图片字节与 MinIO 对象
   一致、`/document-artifacts/{id}/download` 返回 `image/jpeg`。
2. 前端预览里确认 5 处引用都能渲染（浏览器实测 + 截图）。
3. 结果写回设计文档的"实测"小节。

## Task 7：收尾

1. 全量测试 + lint + typecheck + build。
2. CHANGELOG（中文）+ 单个提交；把实测数字写进提交信息。
