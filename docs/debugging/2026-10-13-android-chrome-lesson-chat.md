# Android Chrome 学生讲义 Chat 消失排查记录

记录日期：2026-10-13（Asia/Tokyo）。

状态：真机现象已补充，Chat 根因尚未定位，未实施修复。

## 开发上下文

- worktree：`/Users/seanlee/.config/superpowers/worktrees/langalpha/more-to-skills-textbook-refactor`。
- 分支：`feature/more-to-skills-textbook-refactor`；本次检查基线为 `c4395f6c8`。
- 学生阅读路由：`/education/learn/:assignmentId`，查询参数包含 `kp/node/view`。
- 开发服务：`0.0.0.0:5177`，本轮确认进程来自目标 worktree。
- 早期同名记录暂存在主仓库；本文在指定 worktree 接续调查，取代早期「尚未收到真机回答」的判断。先前的写权限限制不适用于本轮。

## 用户确认的现象

设备为 Android 11 平板，此前报告 Chrome `90.0.4430.210`。

早期反馈：讲义最初有 Chat 输入区，后来消失；讲义正文仍正常，刷新不恢复，Mac 正常。

本轮真机补充：

| Chrome 请求模式 | 讲义 Chat | 讲义导出 PDF 按钮 | 原始教材 PDF |
| --- | --- | --- | --- |
| 普通移动模式 | 看不见 | 可见 | 一直显示「加载原文件」，最多看到页数控件，没有 PDF 页面 |
| 请求桌面版网站 | 可见 | 可见 | 同样一直加载，没有 PDF 页面 |

用户没有提供本轮完整 URL、实际 CSS 视口宽高、页面缩放及故障时 DOM 边界，不能据设备尺寸假定命中了哪个断点。

## 已核对的代码

- `BookLessonReader.tsx` 只有在教材 ID 存在、`view=material`、讲义可用且 Markdown 非空时，渲染 `LessonConversation`；导出按钮也由此分支提供。
- `LessonConversation.tsx` 没有按 Android、Chrome 版本或宽度隐藏整个输入区的条件。会话加载中或失败时仍有禁用输入区，因此接口失败本身不足以解释整块输入区消失。
- `useIsMobile.ts` 的断点为 767px。窄屏启用底栏，外层 `.app-main` 通过底部 padding 留位；学生目录还使用 1024px 的断点。
- `App.css` 的外层高度是 `100vh`，767px 以下追加 `100dvh`。Chrome 90 不支持 dvh，会保留 vh；平板也可能不进入该规则。
- 讲义高度链包含 Grid、Flex、多层 `height:100%`、`min-height:0` 与 `overflow:hidden`。正文滚动区为 flex:1，输入区为 flex-shrink:0。
- 当前外层没有按 Android `visualViewport.height` 调整高度。地址栏、键盘和缩放导致布局视口与可见视口不一致仍是待验证方向。

## 本轮本机验证

实际 macOS Chromium `90.0.4430.0` 访问目标 worktree 的 5177 服务，全部 API 使用合成学生和教材数据拦截，未操作真实账户。

临时诊断脚本 `/tmp/langalpha-student-chat-visibility.mjs` 补齐了新增批注的 items 模拟接口。第一次使用旧脚本时页面未能保持正常挂载，属于诊断数据不完整，不计为问题复现。

补齐后分别使用 Android UA + isMobile 和桌面 UA + 非移动参数，检查长讲义、滚到底部、横屏尺寸、缩小高度、600px 窄屏、聚焦后缩小高度及窄屏刷新：

- 两轮各采集 14 份边界快照；输入区始终存在，底边未超出模拟可见视口，没有捕获到页面或控制台错误。
- 768 × 1024 时，输入区 y=945、高度 79、底边 1024。
- 600 × 850 时，输入区 y=693、高度 79、底边 772，给底栏留出 78px。
- 600 × 350 时，输入区 y=193、底边 272。
- 输出为 `/tmp/langalpha-student-chat-chrome90-mobile.json` 和 `/tmp/langalpha-student-chat-chrome90-desktop.json`；临时文件可能被清理。

这只是本机布局诊断，不是 Android 真机通过。改变模拟 viewport 高度不等于 Android 的地址栏收放或软键盘；桌面 UA 参数也不完整复刻设备的「请求桌面版网站」行为。未测试发送问答或真实教材接口。

## 更新后的判断

1. 导出按钮在两种模式均可见，明显降低了「切到 source 导致 Chat 未设计/未挂载」的可能性；优先检查输入区在 DOM 中的实际位置。
2. Chat 随请求模式变化，重点排查 CSS 断点、vh 与 visualViewport 差异、底栏覆盖及祖先裁剪。尚不能指定某个 CSS 属性为根因。
3. 原书 PDF 在两种模式均失败，呈现出不同于 Chat 的变化规律，应独立排查。已有本机 PDF 引擎兼容证据见 [PDF 记录](2026-10-13-original-pdf-chrome90.md)，不能据此断言真机加载停滞只有一个原因。

## 后续取证

- 同一教材/知识点 URL，对比真机两种模式，采集 `innerWidth/innerHeight/devicePixelRatio`、`visualViewport.width/height/offsetTop/scale`、767px 和 1023px 的 matchMedia 结果。
- 查看 `.lesson-composer` 是否存在；采集其自身、`.lesson-conversation`、滚动区、学生 section、Grid、`.main/.app-main/.app-layout` 的边界、计算高度、overflow 和 scrollTop。
- 核对祖先裁剪与底栏边界，在输入区中心用 elementFromPoint 检查覆盖元素；不能只以 DOM 存在作为可见通过。
- 对照地址栏展开/收起、输入法打开/关闭、横竖屏和刷新前后的上述值。本机尚未复现，下一步优先真机远程调试。
- PDF 单独采集原文件和 worker 请求状态、控制台异常、Document/page 加载回调与 canvas 数量；先确定停在下载、worker 初始化还是页面渲染。

本轮只更新排查文档；没有修改业务代码、数据库、Docker 或运行服务配置。
