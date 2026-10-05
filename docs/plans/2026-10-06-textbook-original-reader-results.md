# 教材原文件阅读验收记录

日期：2026-10-06。实施计划见`2026-10-06-textbook-original-reader.md`。

## 实现结果

- 家长工作台三tab：知识点保留讲义阅读，原书目录打开原PDF，文字目录保留冻结Markdown按行读取；知识点可在正文标题下切到原文件。
- 已有结构无需重新生成。PDF定位优先用起始行对应的冻结分页标记（Datalab零基转一基）；关联多个节点时，JSON回退取最早的明确PDF起始页。未明确页码坐标系的通用page_range不用于自动跳转。
- 无页码、无标记、定位读取失败或页码越界时打开原文件首页；原文件不存在时显示错误、重试及文字目录退路。只读接口校验教材家长归属，再读取唯一关联图书馆文件，允许同家庭另一家长按原上传owner读取；不公开存储键。
- 原文件bytes与定位分开缓存，手动页码写入URL，刷新/切回可恢复，换目录节点重新定位；PDF窄屏适应宽度，放大后左右内容可滚动查看，页码及缩放用图标和本地化tooltip。学生入口仍保留原先两tab与阅读权限。
- 不重新解析、不改Skill/推理强度/切分、无迁移、无付费模型调用或已有教材删除；原文件与冻结原文未写入。

## 验证证据

- 后端聚焦四文件：60 passed（3.12秒），包含真实FastAPI路由的权限服务mock、流式响应关闭、未知定位与参数校验；新服务和HTTP用例先失败再实现。相关Ruff通过。
- 前端最终教育/文档/共享PDF/locale/token相关34文件：285 passed（7.41秒）。类型构建、相关生产文件ESLint及diff检查通过；首屏360.1kB gzip，小于450kB门槛。
- 新原文件浏览器独立七项：7 passed（45.9秒），使用仓库已有PDF页由pypdf在内存生成20页fixture；验证真实react-pdf canvas非空、对应data-page-number及页数，覆盖375/1440亮暗、marker优先、JSON回退、无定位首页、越界首页、错误与文字退路、刷新和切换缓存。
- 最终联合原文件/加工时间线/紧凑布局/学生学习四个文件：35 passed（2.9分钟），进程退出码0。保留初轮34 passed/1 failed记录，修正等待策略后完整重跑通过。
- 检查最终桌面暗色和移动亮色截图，PDF内容可见，三个目录tab、标题/按钮和PDF控制区没有交叠；默认窄屏页宽小于视口，canvas左边界可达。
- 只读取最新一份已有教材，真实PG查询与localhost:9000对象读取验证关联原PDF以`%PDF-`开头，长度2500bytes，首行定位未知。没有枚举全部教材或无关对象；不是重新解析或模型工作流验收。
- 更新后台前确认head `087_book_token_usage`、0活跃教材job和0 `in_progress` run。只停止已核对cwd的本worktree旧8000进程；新版PID27256监听`*:8000`，health HTTP200，新接口未登录HTTP401。前端PID1294为本worktree/web、监听`*:5177`，本机及LAN `192.168.1.252:5177`返回200，保留运行。

## 初轮问题与修正

- PDF fixture直接写stdout因pypdf要求seek而失败，改在BytesIO生成后输出，没有保存或提交生成PDF。
- 375px浏览器先失败：原阅读器canvas居中后左边界为-118.5px；教材opt-in适应宽度与可达滚动后七项通过，其他PDF入口默认尺寸不变。
- 质量审查发现JSON通用页码可能是印刷坐标、学生两tab出现空白第三列；收紧为明确PDF标签并按实际tab数布局，复审无剩余发现。
- 联合初轮34 passed/1 failed，失败停在page.goto等待load事件；带trace聚焦同样超时，trace未形成可读zip，不隐去失败。该用例改等待DOMContentLoaded，并继续验证实际PDFcanvas及页码后聚焦1 passed（8.8秒）；最终联合重跑另记，不用重试结果冒称初轮全绿。
- 新单测初次类型检查指出BookStructureNode缺少显式page_range类型，补充已有schema字段；最终构建通过。Fast Refresh新增警告通过将定位helper移至普通TS模块消除。保留既有React Router、Browserslist、大chunk及Node工具警告。

## 未测与边界

浏览器HTTP/SSE为fixture，真实PDF渲染不等同真实模型全流程。此次未新增付费模型验收、未跑数据库schema重建或PG集成测试、未独立验收生产网络中断时闭流、超大PDF性能及屏幕阅读器；不把一份已有原文件的只读服务检查扩大为所有教材通过。原生Chrome已登录端到端点击未测。

继续当前分支/worktree，不merge/push；用户未提交业务活动文档及PDF不纳入提交，Docker volumes、图书馆原件和解析产物保持原样。
