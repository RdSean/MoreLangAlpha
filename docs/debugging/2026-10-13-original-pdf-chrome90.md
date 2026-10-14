# 原始教材 PDF 在 Chromium 90 的兼容问题

记录始于 2026-10-13，修复于 2026-10-14。分支：`feature/more-to-skills-textbook-refactor`。

## 修复与真机复测（2026-10-14）

后续已实施教材 URL/Range 渐进加载，首屏测量与相关回归见[渐进加载记录](2026-10-14-textbook-pdf-progressive-loading.md)。下文保留引擎兼容修复时的历史验证结果。

状态：已修复；用户确认 Android 11 / Chrome `90.0.4430.210` 在普通模式和「请求桌面版网站」下均能显示原始教材 PDF。学生讲义 Chat 在两种模式也均正常。此结果为用户真机复测，不是本机 UA 模拟。

修复在共享 `PdfViewer` 中同时处理页面和 worker 两个 JavaScript realm：页面先补 `Array.prototype.at` 与 `Promise.withResolvers`；PDF.js 加载后再补 `structuredClone`，避免 PDF.js 的 `ArrayBuffer.transfer` 回退与 structured-clone 补丁递归。PDF.js 切换到 legacy API，worker 自带 realm 内补丁并经 Vite 转译到 Chrome 90 可解析的语法。保留 worker 正常导出，保证浏览器禁用 Worker 时 PDF.js 的主线程回退可用。

同时将 PDF.js 等待 `numPages` 后才挂载页面，并把页码限制到实际页数，避免文档加载期间旧页码短暂超出新文档范围；原文件、页面读取及绘制错误均传入已有重试错误边界。

验证包括实际 Chromium 90 的 38 项原书与浏览器兼容回归、8 项真实生产包专项检查，以及当前 Chromium 的 41 项回归；实际 legacy worker 有返回且 canvas 含非空页面像素，扫描版、图片版及图文混排 PDF 均可显示。生产构建、33 项聚焦单元检查、类型检查、修改文件 ESLint 通过。构建首屏 432.7 kB gz / 450 kB 预算。LAN `192.168.3.240:5177` 可访问。回滚 tag：`v2026.10.13-before-pdf-chrome90-fix`，指向改动前基线 `aa5e8ef0e`。

用户反馈在两种 Chrome 模式下现在均能加载，但速度较慢，怀疑与原文件较大有关。当前没有分段下载/Range 请求的时序数据，不能确认瓶颈在文件体积、传输、PDF.js 解析还是页面绘制；本修复没有加入性能优化。若需继续优化，先记录原文件响应大小与耗时、Document `onLoadSuccess` 耗时和首个 canvas 绘制耗时，再决定是否支持 HTTP Range 或渐进式加载。

## 修复前现象

学生「原始教材」切换至家长端同款 PDF 阅读器后，在当前 Chromium 正常显示。实际 macOS Chromium `90.0.4430.0` 下，学生和家长原书阅读都显示「原文件暂不可读，请重试或切换文字目录」。页面与目录本身正常，错误被 `DocumentErrorBoundary` 捕获，PDF canvas 未生成。

这与 Android 11 / Chrome `90.0.4430.210` 上「讲义可见但 Chat 消失」的报告应分别排查；本记录不证明两者同源。

## 真机修复前现象（2026-10-13）

用户已复测 Android 平板：普通模式和「请求桌面版网站」都一直显示「加载原文件」，最多看到页数控件，没有 PDF 页面。与之不同，讲义 Chat 在桌面请求模式可见、普通模式不可见，两种模式的讲义「导出 PDF」按钮均可见，详见 [Chat 记录](2026-10-13-android-chrome-lesson-chat.md)。

这是修复前用户确认的真机现象。真机的持续加载与下述 macOS Chromium 90 的错误提示表现不同；页数控件存在不代表 PDF canvas 已渲染，也不足以证明下载或 worker 已完成。修复后的真机结果见本记录开头。

后续需分别记录原文件/worker 请求状态、控制台异常、文档与页面加载回调、canvas 数量，确定停在下载、worker 初始化还是页面渲染，再验证主线程与 worker 的完整兼容。

## 修复前实测证据

- 使用原书浏览器测试的合成 20 页 PDF，原文件 API 返回 PDF，现代 Chromium 的 canvas 非空、翻页、刷新与主题回归通过。
- 指定旧内核运行 `web/e2e/education-textbook-original.spec.js` 时，家长与学生 PDF 渲染均失败，缺失 canvas；此运行不计为通过，部分用例未运行。
- 另用旧内核打开目标 worktree 的 `127.0.0.1:5177`，仅拦截 API 使用合成学生 / 教材数据和仓库测试 PDF，未读写真实账户或教材。
- 控制台错误：`TypeError: undefined is not a function`，首个堆栈位置为 `react-pdf.js` 的 `PDFDocumentLoadingTask` 实例字段初始化。
- 对应依赖代码为 `_capability = Promise.withResolvers()`；Chromium 90 缺少该 API。`DocumentErrorBoundary` 随后捕获错误，PDF canvas 数量为 0。

## 修复前判断（历史记录）

当时确认至少一个阻断原因是 PDF.js 主线程调用现代 Promise API。家长与学生共用同一阅读器，因此都受影响，不能将当时的故障归因于学生分配权限或新 tab 状态。

仅补 `Promise.withResolvers` 不足以证明完整兼容；后续实际 worker 测试又发现 worker 语法和独立 realm API 要求。修复及验证结果见本文开头。

学生原书入口与权限属于之前已交付内容，Markdown 保留在「文字目录」。本次兼容改动集中在共享文档阅读模块，并以实际旧内核验证 PDF canvas，同时检查开发环境和生产构建。

## 复测入口

```bash
cd web
PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH='/tmp/langalpha-chromium90/chrome-mac/Chromium.app/Contents/MacOS/Chromium' pnpm test:e2e e2e/education-textbook-original.spec.js --project=chromium
```

旧内核路径属于本机临时安装，运行前先确认存在。已覆盖家长 / 学生、Quiet / NASA、多种视口、页码定位、刷新恢复、PDF 与文字切换；用户也已确认 Android 平板普通及桌面请求模式均能显示。
