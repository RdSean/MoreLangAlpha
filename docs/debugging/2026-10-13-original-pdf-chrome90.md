# 原始教材 PDF 在 Chromium 90 的兼容问题

日期：2026-10-13。分支：`feature/more-to-skills-textbook-refactor`。

## 现象

学生「原始教材」切换至家长端同款 PDF 阅读器后，在当前 Chromium 正常显示。实际 macOS Chromium `90.0.4430.0` 下，学生和家长原书阅读都显示「原文件暂不可读，请重试或切换文字目录」。页面与目录本身正常，错误被 `DocumentErrorBoundary` 捕获，PDF canvas 未生成。

这与 Android 11 / Chrome `90.0.4430.210` 上「讲义可见但 Chat 消失」的报告应分别排查；本记录不证明两者同源。

## 真机补充（2026-10-13）

用户已复测 Android 平板：普通模式和「请求桌面版网站」都一直显示「加载原文件」，最多看到页数控件，没有 PDF 页面。与之不同，讲义 Chat 在桌面请求模式可见、普通模式不可见，两种模式的讲义「导出 PDF」按钮均可见，详见 [Chat 记录](2026-10-13-android-chrome-lesson-chat.md)。

这是用户确认的真机现象，不是本机复现的新结论。真机的持续加载与下述 macOS Chromium 90 的错误提示表现不同；已有 `Promise.withResolvers` 阻断证据仍成立，但尚不能断言它完全解释真机停滞。页数控件存在不代表 PDF canvas 已渲染，也不足以证明下载或 worker 已完成。

后续需分别记录原文件/worker 请求状态、控制台异常、文档与页面加载回调、canvas 数量，确定停在下载、worker 初始化还是页面渲染，再验证主线程与 worker 的完整兼容。

## 实测证据

- 使用原书浏览器测试的合成 20 页 PDF，原文件 API 返回 PDF，现代 Chromium 的 canvas 非空、翻页、刷新与主题回归通过。
- 指定旧内核运行 `web/e2e/education-textbook-original.spec.js` 时，家长与学生 PDF 渲染均失败，缺失 canvas；此运行不计为通过，部分用例未运行。
- 另用旧内核打开目标 worktree 的 `127.0.0.1:5177`，仅拦截 API 使用合成学生 / 教材数据和仓库测试 PDF，未读写真实账户或教材。
- 控制台错误：`TypeError: undefined is not a function`，首个堆栈位置为 `react-pdf.js` 的 `PDFDocumentLoadingTask` 实例字段初始化。
- 对应依赖代码为 `_capability = Promise.withResolvers()`；Chromium 90 缺少该 API。`DocumentErrorBoundary` 随后捕获错误，PDF canvas 数量为 0。

## 当前判断与改动边界

已确认至少一个阻断原因是现有 PDF.js 主线程使用现代 Promise API。原书阅读复用的 `PdfViewer.tsx` 与 `pdfjs-dist/build/pdf.worker.min.mjs` 本次没有修改，因此家长端已有同样限制，不能将此表现归因于学生分配权限或新 tab 状态。

仅补 `Promise.withResolvers` 不足以证明完整兼容：还需检查 worker 中相同 API、新语法和其他现代 API。当前证据只确认最早暴露的失败点，不声明它是唯一原因。

本次只交付学生原书 PDF 入口与权限，Markdown 保留在「文字目录」。后续修复应限制在共享文档阅读模块，并用实际旧内核验证 PDF canvas，而非仅模拟删除 API；开发服务与生产构建都应覆盖。

## 复测入口

```bash
cd web
PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH='/tmp/langalpha-chromium90/chrome-mac/Chromium.app/Contents/MacOS/Chromium' pnpm test:e2e e2e/education-textbook-original.spec.js --project=chromium
```

旧内核路径属于本机临时安装，运行前先确认存在。修复后应覆盖家长 / 学生、Quiet / NASA、375 / 768 / 1440px、页码定位、刷新恢复、PDF 与文字切换，以及用户 Android 平板的真实显示。
