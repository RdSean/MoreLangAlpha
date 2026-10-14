# 教材 PDF 渐进加载与性能验证

日期：2026-10-14。分支：`feature/more-to-skills-textbook-refactor`。

## 基线与范围

此前教材阅读器通过 Axios 完整取得 ArrayBuffer，再挂载 PDF.js。用户确认 Chrome 90 兼容修复后普通/桌面请求模式均可阅读，但大文件加载偏慢。

回退检查点 `v2026.10.14-before-pdf-progressive-loading` 指向 `efe0365f9`，包含已验证的 Chrome 90 修复。实现计划见 [开发计划](../plans/2026-10-14-textbook-pdf-progressive-loading.md)。

不改 Docker、数据库或主题。MinIO 沿用当前 worktree 的 .env 配置；没有对浏览器暴露 MinIO 地址、key 或签名 URL。

## 已实现行为

- 教材接口返回完整 200、单段 206 或不可满足范围的 416。开放范围、尾部范围、范围末端截断与 If-Range 强 ETag/日期校验均有合同检查；不支持的单位、多段或畸形 Range 回退完整 200。
- 每次请求都经过家庭/教材分配权限检查，再读文档元数据或对象。MinIO GetObject 直接附带规范化 Range 和 IfMatch，不下载全文件后截取；HEAD/GET 间版本改变或返回范围/长度不一致时关闭流并报错重试。
- 成功响应保留 private/no-store 和 Cookie 认证，Content-Encoding: identity 避免 GZip 改变字节与长度；CORS 显式暴露范围读取响应头。实际开发后端的认证失败响应也已核对 CORS 头，没有放宽 allowed origins。
- BookOriginalReader 将 URL 交给 PDF.js，不等待全量 React Query bytes。原书对照共用同一路径，页码定位仍使用原有查询；保留字节输入供文档库等阅读器使用。
- 保留 Chrome 90 legacy 引擎、兼容补丁顺序及 worker 回退。默认允许流读取和后台预取，rangeChunkSize 沿用 PDF.js 的 64 KiB。
- 阅读器卸载会销毁当前 PDF.js 文档并取消未完成请求，重试只重建阅读器；退出/重新打开原书可能重新请求文件，不再依赖全量字节缓存。没有加入跨视图、离线或跨账户的 PDF 缓存。

## 取证与性能

### 可控大文件红绿验证

测试生成 32 页合法 PDF，约 6.31 MB，包含实际图像与可识别正文；每块全量数据设置延迟，由真实 HTTP 流服务返回。Playwright route.fulfill 会缓冲整个 body，不能替代该服务证明流式显示。

旧实现中第 12 页显示时全量响应已结束；“完整响应尚未结束即显示目标页”的检查按预期失败。切换 URL 加载后，同一检查通过，目标页 canvas 有实际像素且带认证 Cookie 的 Range 请求确实发生。检查还要求首次可读前所有响应已传字节总和小于文件大小，避免仅看一条未完成全量请求而误判。

### 真实教材只读范围验证

用户此前提供的教材对应原文件为 33,027,005 字节，约 31.50 MiB。使用现有教育服务与创建者的教材权限检查，只读下载并核对头部、中段、尾部各 64 KiB；字节内容与原文件一致。

此次服务层完整下载约 465 ms，三段读取约 32 / 32 / 28 ms。这只是本机后端至 MinIO 的取证数据，不包含浏览器、Wi-Fi、页面解析和图像解码，不等于首屏时间。

### 真实文件的浏览器对照

使用上述同一份文件的临时本地副本，经带 Cookie/CORS 的测试 HTTP 服务加载。完整缓冲基线在返回 PDF.js 之前等所有字节到齐，复现旧阅读器的等待合同；渐进模式直接加载 URL。两种模式分别测 3 次，首次为冷页面，其后为暖页面；每个 64 KiB 数据块延迟 1 ms。

| 模式 | 第一次首次可读 | 第二次 | 第三次 | 中位数 |
| --- | --- | --- | --- | --- |
| 完整缓冲 | 5,570 ms | 2,111 ms | 2,097 ms | 2,111 ms |
| 渐进 URL | 2,148 ms | 1,098 ms | 1,122 ms | 1,122 ms |

中位数缩短约 47%。渐进第二、第三次首次可读前分别累计传输约 12.12 MB、13.24 MB，完整响应尚未结束；第一次完整流已完成，并有重复范围数据，累计传输约 34.01 MB。后台预取和范围请求可以增加最终流量，本次不承诺减少总下载字节。

这些是实际教材内容在受控本机服务中的结果，不是用户 Android 真机或实际生产链路的端到端指标；冷页面启动、网速、PDF 结构和图像解码均会影响表现。

## 测试记录

- 后端聚焦检查：145 项通过，包括 Range/If-Range、文件版本、范围和长度一致性、原有文档下载及导入分层。
- 真实 MinIO 与 HTTP 生命周期：2 项通过。临时对象使用唯一 education 测试 key，检查后已明确清理；没有枚举、覆盖或删除真实教材。
- 前端单元检查：37 项通过；TypeScript 与生产构建通过，首屏 432.6 kB gzip / 450 kB 预算。
- 渐进、Range 不支持的完整回退、取消读取、权限错误/手工重试：4 项浏览器检查通过。
- 真实文件性能探针：2 项通过，各模式包含 3 次测量。
- 当前 Chromium 与真实 macOS Chromium 90.0.4430.0 的全套各 45 项通过，各有 2 项可选性能探针默认跳过；两套主题、家长/学生、多种视口、页码恢复、原书对照/Chat、键盘/滚轮与缩放均纳入回归。
- 修改文件 Ruff/ESLint 通过。实际 Chromium 90 的生产包 12 项专项检查通过，覆盖 worker、回退、扫描/图片/混排 PDF 与渐进读取；手机家长、桌面学生截图及 canvas 非空像素已核对。
- 指定 worktree 的开发服务继续监听 `0.0.0.0:5177`，LAN `http://192.168.3.240:5177` 返回 200。隔离生产预览已停止，Android 真机复测待用户反馈。

中间验证中，已有回归的全量缓存次数预期与新文档生命周期不一致，已更新为每次阅读器挂载一次请求，翻页不重取整文件。导航等待 load 在后台流读取时出现超时，回归改为等待 DOMContentLoaded 后核对 canvas 非空像素、页码和实际交互，不能用全量资源结束作为渐进显示前提。新增取消测试最初未指定中文 locale，找不到中文 tab，属于测试配置问题，补齐后通过。上述失败运行均不计为验收成功。

## 复测命令

```bash
# worktree root
RUN_DOCUMENT_MINIO_TESTS=1 uv run pytest -m integration tests/integration/test_education_pdf_range_minio.py tests/integration/test_education_pdf_stream_lifecycle.py -q

# web; run sequentially because suites share mock ports
pnpm test:e2e e2e/education-textbook-pdf-progressive.spec.js e2e/education-textbook-original.spec.js e2e/browser-compatibility.spec.js --project=chromium
PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH=/tmp/langalpha-chromium90/chrome-mac/Chromium.app/Contents/MacOS/Chromium pnpm test:e2e e2e/education-textbook-pdf-progressive.spec.js e2e/education-textbook-original.spec.js e2e/browser-compatibility.spec.js --project=chromium
```

性能探针默认跳过。显式提供 `PDF_PERF_BENCHMARK=1`、只读本地 `PDF_PERF_FIXTURE`，以及可选 `PDF_PERF_DELAY` 后运行 `--grep 'performance probe'`；不提交教材副本。临时文件可能已在验收后清理。

本轮真实教材临时副本与只读探针脚本已清理，文档仅保留大小、时间与字节核对结果，不保留教材正文或账户凭据。

## 后续与回退

Android 11 / Chrome 90.0.4430.210 需刷新后分别检查普通/桌面模式，确认原书、对照、翻页和 Chat 仍正常。只有用户实际反馈才计为新功能真机验收。

前端切换提交可独立 revert，恢复原有完整 bytes 读取；后端仍接受完整请求，Chrome 90 引擎修复不受影响。可根据真机的首屏时间和请求次数再调整 chunk 大小或预取策略；本轮不进行 PDF 重压缩、线性化加工或预览图生成。
