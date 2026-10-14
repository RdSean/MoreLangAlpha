# 教材 PDF 渐进加载开发计划

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 教材原书及讲义对照通过认证接口渐进加载 PDF，使大教材在完整文件下载结束前显示目标页，并保留 Chrome 90 的已验证兼容性。

**Architecture:** PDF.js 直接请求教材原文件 URL，FastAPI 校验家庭与教材访问权限后，将单段 HTTP Range 转为 MinIO/S3 GetObject Range。完整请求仍可返回 200，分段请求返回 206；前端保留现有字节输入入口，文档库等其他阅读器调用不切换加载方式。

**Tech Stack:** React 19、react-pdf 10.3、pdfjs-dist 5.4.296 legacy、Vite、FastAPI/Starlette、boto3、MinIO、pytest、Vitest、Playwright。

---

## 开发边界与基线

- 工作目录：`/Users/seanlee/.config/superpowers/worktrees/langalpha/more-to-skills-textbook-refactor`。
- 分支：`feature/more-to-skills-textbook-refactor`；计划基线：`300f8d614`。
- Chrome 90 修复前的历史 tag：`v2026.10.13-before-pdf-chrome90-fix`。本次实施前另打基于当前 HEAD 的本地检查点，避免回退时丢失已修复的 Chrome 90 能力。
- 用户已确认 Android 11 / Chrome 90.0.4430.210 的普通/桌面请求模式中 PDF 与 Chat 均正常；本次是加载性能升级。
- 不改 Docker、数据库或 Alembic，不修改 PTC/Flash/SSE/checkpoint，不调整 Quiet/NASA 主题。
- 不新建 PDF 加工流水线，不做线性化、压缩或逐页图片生成；不加入 Service Worker、IndexedDB 或跨会话 PDF 缓存。
- 读取现有 `STORAGE_*` 配置，不打印凭据、不枚举或修改真实教材对象。新增教育测试对象使用唯一 `education/tests/pdf-range/<uuid>/` 前缀，只清理本次创建的明确 key。
- 不提交当前无关的业务计划改动、parquet 或本地教材 PDF。

## 已确认现状

1. `web/src/pages/Education/api.ts` 的 `getManagedBookOriginal()` 用 Axios `responseType: 'arraybuffer'` 完整下载原文件。
2. `BookOriginalReader.tsx` 等待 React Query 返回全部字节后才挂载 `PdfViewer`；`PdfViewer.tsx` 将字节复制后交给 worker，不能自行请求服务器片段。
3. `src/server/app/education/textbooks.py` 原文件接口返回全量 StreamingResponse，未处理 Range。
4. `src/utils/storage/s3_compatible.py` 的 `open_download_stream()` 调用 GetObject 时没有 Range；MinIO 原生支持分段读取。
5. `src/server/app/setup.py` 全局启用 GZip；PDF.js 只有看见正确的 Content-Length、Accept-Ranges: bytes 和 identity 内容编码才启用 Range。
6. API 使用 Cookie 认证；当前 CORS 允许 credentials 和请求头，但未暴露 Range 相关响应头。

## 固定交互与协议合同

### 加载与认证

```text
家长/学生原书或讲义对照
  -> PDF.js 请求 /api/v1/education/textbooks/{id}/original
  -> Cookie 认证 + 家庭/学生教材分配校验
  -> 200 全流 / 206 单段流
  -> MinIO GetObject（单段请求附带 Range）
```

客户端不接收 storage key、MinIO 地址或签名 URL。每次 Range 请求都检查当前访问权限，不能以首次请求通过替代后续校验。

### HTTP 行为

| 请求 | 响应及行为 |
| --- | --- |
| 无 Range | 200，全文件流；Accept-Ranges: bytes、Content-Length 为完整长度 |
| bytes=0-1023 | 206，返回闭区间；Content-Range: bytes 0-1023/N，Content-Length: 1024 |
| bytes=1024- | 206，从 1024 至文件末尾 |
| bytes=-1024 | 206，最后至多 1024 字节 |
| end 超过文件末尾、start 有效 | 截断 end 至 N-1 |
| start >= N / bytes=-0 / 空文件上的有效范围 | 416，Content-Range: bytes */N |
| 不支持的单位、多段、畸形/反向范围 | 忽略 Range，返回完整 200；不拼 multipart，也不返回伪造 206 |
| If-Range 与当前强 ETag 或 Last-Modified 相符 | 返回请求范围 |
| If-Range 失配、弱 ETag 或不可解析 | 忽略 Range，返回完整 200 |
| 未认证、跨家庭、未分配或权限撤销 | 沿用现有认证与不可访问状态，禁止读取对象或泄露长度/ETag |

所有成功 PDF 响应保持 `Cache-Control: private, no-store`、`X-Content-Type-Options: nosniff` 和现有文件名处理。原文件流使用 `Content-Encoding: identity` 绕过现有 Starlette GZip，不能只加 no-transform 后假定 GZip 已停止。206 的长度必须是片段长度，不是文件总长。

第一版允许 PDF.js 后台预取：保持 disableRange=false、disableStream=false、disableAutoFetch=false，不承诺网络只读取当前页。先沿用 PDF.js 默认 rangeChunkSize（64 KiB）；测量 Range 次数与局域网延迟后再决定是否改为 256 KiB 等，不在第一版添加用户设置。

## Task 1: 记录基线并建立性能验收样本

**Files:**
- Create: `docs/debugging/2026-10-14-textbook-pdf-progressive-loading.md`
- Create: `web/e2e/education-textbook-pdf-progressive.spec.js`
- Create: `web/e2e/helpers/pdfRangeServer.js`（只供测试的可节流 HTTP 服务）
- Reuse: `web/e2e/helpers/textbookProcessingFixtures.js`
- Reuse: `tests/fixtures/documents/{text,scanned,image-based,mixed}.pdf`

1. 核对分支、HEAD、dirty files；创建本地 tag `v2026.10.14-before-pdf-progressive-loading`，不推送。
2. 在现有浏览器 mock 体系中增加可控的大 PDF 与慢速全量响应样本；样本在测试期间生成，不提交真实教材或巨型二进制。大样本必须含可识别目标页，不能只追加无效尾部字节充当效果证据。
3. 记录下载开始、响应头到达、全量下载结束、Document 成功及首个目标页 canvas 非空的时间；分清冷启动 worker/懒加载与暖启动，固定同一网络条件。
4. 先证明旧实现的首个 canvas 出现于全量字节返回之后；加入“全量流尚未完成时目标页已经显示”的验收，确认它在旧代码下失败。
5. 对实际大教材做只读计时，记录大小与耗时，不记录正文、凭据或私有对象 key；不要把 mock 中的加速数字当成实际教材结果。

Run from `web/`:

```bash
pnpm test:e2e e2e/education-textbook-pdf-progressive.spec.js --project=chromium --max-failures=1
```

Expected before implementation: 新增渐进显示验收失败；其余取证可执行。调试文档明确标注基线结果。

## Task 2: 单段 Range 解析与存储能力

**Files:**
- Create: `src/server/documents/http_range.py`
- Create: `tests/unit/server/documents/test_http_range.py`
- Modify: `src/utils/storage/s3_compatible.py`
- Modify: `src/server/documents/storage.py`
- Modify: `tests/unit/utils/storage/test_s3_compatible.py`
- Modify: `tests/unit/server/documents/test_storage.py`

1. 先为上表 Range 合同编写参数化失败测试：1 字节、完整范围、超长 suffix、开放范围、无效 start、反向范围、多段、不支持单位及空文件。整数转换前限制 Range 头长度，避免异常长数字触发转换错误。
2. 在纯函数模块定义闭区间结果及“不可满足”异常；输出用于规范化 S3 Range，不让原始 HTTP 字符串直接进入存储调用。
3. 给 S3 封装增加只读对象元数据能力及可选字节范围下载，元数据含完整长度、ETag、Last-Modified；GetObject 按规范化 Range 调用。
4. 扩展 `DocumentObjectStore`，提供元数据与范围读取能力。保持现有 `open_download(key)` 调用及注入测试接口兼容，既有全量读取不强制多一次 HEAD。
5. 分段读先取得元数据，用同一对象的 ETag/版本约束实际 GET；处理 HEAD 与 GET 之间对象变化，禁止用旧长度拼接新对象片段。S3 412/对象变更返回可重试失败，不伪装成功。
6. 响应流公开片段长度、完整长度和实际范围；同步 boto3 I/O 保持在线程中，关闭操作幂等，并覆盖流正常结束、读取失败与提前关闭。

Proposed range contract:

```python
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ByteRange:
    start: int
    end: int

    @property
    def length(self) -> int:
        return self.end - self.start + 1

    @property
    def s3_header(self) -> str:
        return f"bytes={self.start}-{self.end}"
```

Run from worktree root:

```bash
uv run pytest tests/unit/server/documents/test_http_range.py tests/unit/server/documents/test_storage.py tests/unit/utils/storage/test_s3_compatible.py -q
```

Expected: 红测确认后实现，相关用例全绿；断言 boto3 收到 Range，响应内容等于预期切片，没有先下载全量后截取。

## Task 3: 教材接口与权限链路接入

**Files:**
- Modify: `src/server/documents/library.py`
- Modify: `src/server/services/education_book_original.py`
- Modify: `src/server/app/education/textbooks.py`
- Modify: `src/server/app/setup.py`（仅 CORS expose_headers）
- Modify: `tests/unit/server/documents/test_library.py`
- Modify: `tests/unit/server/services/test_education_book_original.py`
- Modify: `tests/unit/server/app/education/test_textbooks.py`

1. 先写失败测试，确认家庭/教材权限校验发生在 metadata 与 GetObject 之前；完整、Range 和 If-Range 路径都覆盖未分配学生、其他家庭及权限撤销。
2. 经现有 library 和 education service 传递可选 Range/If-Range，业务服务决定读取模式，路由只编排请求与响应；不新增第二套所有者查询或直接读取任意 key 的接口。
3. 按合同返回 200/206/416、Content-Range、准确长度、ETag/Last-Modified，保留既有异常映射。Range 越界只能在权限校验之后暴露完整长度。
4. 原文件响应显式 identity，测试请求包含 Accept-Encoding: gzip 时 body 仍为原始 PDF 且 Content-Length 不被删除。
5. CORS 只增加明确响应头：Accept-Ranges、Content-Range、Content-Length、Content-Encoding、ETag、Last-Modified；保留现有 allowed_origins、credentials 和请求头策略，不放宽来源。
6. 以真实 app 中间件栈验证 GET、跨域预检及可读响应头；覆盖完整流、分段流、取消、异常时存储 body 释放。取消测试不得只依赖把整个响应缓冲完的 TestClient。

```bash
uv run pytest tests/unit/server/documents/test_library.py tests/unit/server/services/test_education_book_original.py tests/unit/server/app/education/test_textbooks.py tests/unit/server/app/test_documents_api.py -q
```

Expected: 教材 Range 行为通过，既有文档原文件/产物下载仍全量且合同不变。验证通过后更新中文 CHANGELOG，提交一个后端原子变更。

## Task 4: 教材前端改用 PDF.js URL 加载

**Files:**
- Modify: `web/src/pages/Education/api.ts`
- Modify: `web/src/pages/Education/components/BookOriginalReader.tsx`
- Modify if required: `web/src/pages/Education/queries.ts`
- Modify: `web/src/pages/ChatAgent/components/viewers/PdfViewer.tsx`
- Modify: `web/src/pages/Education/__tests__/BookOriginalReader.test.tsx`
- Create: `web/src/pages/Education/__tests__/bookOriginalSource.test.ts`
- Modify: `web/src/pages/ChatAgent/components/viewers/__tests__/PdfViewer.test.tsx`
- Modify: `web/src/pages/ChatAgent/components/viewers/__tests__/PdfViewerErrors.test.tsx`

1. 先写失败测试：教材 reader 不等待完整字节，PDF.js 收到正确 URL 和 withCredentials=true；API 地址支持同源空 baseURL 及 VITE_API_BASE_URL 分离部署。
2. URL 构造放教育 API 层，复用共享 client 的 baseURL；以教材 ID 构造 URL，组件内不拼接口、不增加 Bearer token。
3. PdfViewer 使用互斥 props 支持原有 `data` 和新增 `source`，禁止两者同时存在；对 source/file/options 做稳定引用，避免父组件重渲染触发再次加载。
4. 保留字节复制与防 detached buffer 机制，既有 Documents/产物预览继续走 data；保留所有 Chrome 90 legacy/polyfill/worker import 顺序。
5. BookOriginalReader 直接挂载 URL 阅读器，继续从 React Query 读取页码定位；重试只重建当前阅读器，不刷新 Chat 或清空草稿。移除教材 reader 对全量 bytes query 的依赖，不为无用清理重构其他下载 API。
6. 初始未取得页数、越界页、媒体类型错误、网络/权限错误仍进入既有 loading/retry 分支。Range 不可用时 PDF.js 接受 200 全量响应；403/404 不自动反复全量重试。
7. 卸载、切换教材及重试时销毁旧 PDF.js loading task 并取消请求；取消不显示故障弹窗。两个对照视图不新增跨账户全局 PDFDocumentProxy 或字节缓存。

Proposed props contract:

```ts
type PdfInput =
  | { data: ArrayBuffer | Uint8Array; source?: never }
  | { source: { url: string; withCredentials: true }; data?: never };
```

Run from `web/`:

```bash
pnpm test src/pages/Education/__tests__/BookOriginalReader.test.tsx src/pages/Education/__tests__/bookOriginalSource.test.ts src/pages/ChatAgent/components/viewers/__tests__/PdfViewer.test.tsx src/pages/ChatAgent/components/viewers/__tests__/PdfViewerInteraction.test.tsx src/pages/ChatAgent/components/viewers/__tests__/PdfViewerErrors.test.tsx src/pages/Documents/__tests__/DocumentPreviewDrawer.test.tsx src/lib/__tests__/browserCompatibility.test.ts
pnpm typecheck
```

Expected: URL 模式与旧 data 模式均通过，不改变翻页、缩放、适配与错误反馈合同。

## Task 5: 真实 MinIO 和浏览器渐进验收

**Files:**
- Create: `tests/integration/test_education_pdf_range_minio.py`
- Update: `web/e2e/helpers/pdfRangeServer.js`（加入 Range、取消和异常场景）
- Update: `web/e2e/education-textbook-pdf-progressive.spec.js`
- Update: `web/e2e/education-textbook-original.spec.js`
- Update: `docs/debugging/2026-10-14-textbook-pdf-progressive-loading.md`

1. 仿照现有 opt-in MinIO 测试，使用本机 .env 存储配置；存储封装集成测试只在唯一 education 测试 key 下写入合成 PDF，并于 finally 清理这些 key。不要为了测试放宽 DocumentObjectStore 现有 documents key 校验；教材真实接口联调只读已有授权教材，不写真实教材或创建数据库记录。测试不依赖历史 192.168.3.164 地址，不改变服务配置。
2. 验证 MinIO 返回头、中、尾真实字节，后端 206 与原始内容逐字节一致；测试经中间件的 identity、准确 Content-Length 与关闭行为。
3. 浏览器的 mock 原文件接口支持 200/206/416 并记录 Range。人为延迟全量流，目标页 canvas 必须在全量完成之前包含可识别内容；同时断言真实 worker 无兼容错误。仅发现一条 Range 请求不能算渐进验收通过。
4. 为可控样本增加节流测试服务，记录连接/请求的取消；Playwright route.fulfill 缓冲整个 body，不能用它证明真实流式首屏与主动取消。样本测试参数需能稳定区分全量结束和目标页绘制事件。
5. 测试 Range 不可用/200 回退、403/404、无效 PDF、重试、快速跳页、离开页面、桌面对照；Quiet/NASA 与家长/学生回归沿用已有 suite。
6. 使用 cookie 的同源和分离 API origin 两种浏览器环境，验证 CORS 暴露头后实际发生 Range；不只测同源 dev proxy。
7. 当前 Chromium、真实 macOS Chromium 90、生产构建各自验证文字/扫描/图片/混排 PDF。最后请用户在 Android 真机普通/桌面模式复测，区别本机模拟与真机证据。

```bash
# root; only new, uniquely prefixed test objects are created
RUN_DOCUMENT_MINIO_TESTS=1 uv run pytest tests/integration/test_education_pdf_range_minio.py -q

# web; suites share mock ports, execute sequentially
pnpm test:e2e e2e/education-textbook-pdf-progressive.spec.js e2e/education-textbook-original.spec.js e2e/browser-compatibility.spec.js --project=chromium --max-failures=1
PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH=/tmp/langalpha-chromium90/chrome-mac/Chromium.app/Contents/MacOS/Chromium pnpm test:e2e e2e/education-textbook-pdf-progressive.spec.js e2e/education-textbook-original.spec.js e2e/browser-compatibility.spec.js --project=chromium --max-failures=1
pnpm build
```

旧浏览器路径属于本机临时安装，先确认存在。生产预览使用隔离 mock API，不发布测试 dist；验证结束停止临时预览，保留 0.0.0.0:5177 LAN 服务。

## Task 6: 性能对照、文档与交付

**Files:**
- Update: `docs/debugging/2026-10-14-textbook-pdf-progressive-loading.md`
- Update: `docs/debugging/2026-10-13-original-pdf-chrome90.md`（增加后续优化链接，保留历史证据）
- Update: `CHANGELOG.md`

1. 同一实际教材与可控样本分别冷启动/暖启动至少测 3 次，记录目标页首次可读中位时间、完整文件大小、首次可读前已传字节、Range 请求数及最终总流量。允许后台最终下载全文件，不把“总流量不降”误判为首屏失败。
2. 主要验收：可控大 PDF 未完成全量传输时目标页已可读；真实大教材首屏时间相对基线改善。实际改善幅度据测量报告，不提前承诺固定秒数；如果首屏主要耗在图片解码，则如实报告并另开优化计划。
3. 检查当前/旧 Chromium 单页和原书对照截图及 canvas 像素；原有 Chat、页码恢复、键盘/滚轮、Ctrl 缩放无回归。
4. 对修改文件跑 Ruff/ESLint，运行 `git diff --check`；生产构建的 critical path 继续满足 450 kB gzip 预算，不抬高预算。
5. 验证服务来自指定 worktree、监听 0.0.0.0:5177；`curl` 检查 `http://192.168.3.240:5177`，并通过 LAN 实际登录只读查看目标教材。
6. 写中文 CHANGELOG 和实测结果，提交前端与验收原子变更；列出 commit、检查点 tag、成功/未验证项目及加载表现。无需合并或推送。

## 回退与后续边界

- 后端 Range 能力是加法：原有未携带 Range 的请求仍返回完整 200，旧前端可继续使用。
- URL 渐进方式出现回归时，可独立 revert 前端切换提交，恢复既有 React Query 全量 bytes 路径，不回退 Chrome 90 引擎修复；保留现有 getManagedBookOriginal 完整下载函数直至此次真机验收完成。
- 不对权限错误启用自动回退，不用后台全量下载掩盖片段损坏；明确失败并支持用户重试。
- 后续再依据测量决定是否调整片段大小、关闭自动预取（需同时处理 disableStream）、预取邻页、PDF 线性化/压缩或预览图。本轮不展开这些功能。
