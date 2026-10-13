# 原始教材 PDF 在 Chromium 90 的兼容问题

日期：2026-10-13。分支：`feature/more-to-skills-textbook-refactor`。

## 现象

学生「原始教材」切换至家长端同款 PDF 阅读器后，在当前 Chromium 正常显示。实际 macOS Chromium `90.0.4430.0` 下，学生和家长原书阅读都显示「原文件暂不可读，请重试或切换文字目录」。页面与目录本身正常，错误被 `DocumentErrorBoundary` 捕获，PDF canvas 未生成。

这与此前 Android 11 / Chrome `90.0.4430.210` 上「讲义可见但 Chat 消失」的报告应分别排查；本记录不证明两者同源，也不表示用户 Android 设备已复测。

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
