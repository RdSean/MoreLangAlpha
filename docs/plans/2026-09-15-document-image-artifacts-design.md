# 文档图片落盘（Datalab 提取图片成为 artifact）— 设计

> 承接 `2026-09-14-datalab-document-parser-design.md` 的 D9 / D9a：当时刻意
> 把图片提取默认关掉，因为提取出来也**没有地址**（SDK 返 base64，markdown 写
> 的是裸文件名），预览必然裂图。这份文档把那个"以后要做"补齐。

## 现状（实测，2026-09-15）

用 `RE3 Part.pdf`（2.98 MB / 5 页）开提取跑真实转换：

| 观测 | 值 |
|---|---|
| 返回图片 | 6 张，base64，合计 0.71 MiB（最大 359 KiB，最小 9.6 KiB） |
| markdown 引用 | 5 处，形如 `![描述](43012ae8…_img.jpg)` |
| 未被引用的图片 | 1 张（SDK 仍然返回） |
| 单次费用 | 2.0 分 |

结论：**引用是相对文件名，图片字节在响应体里，没有任何 URL。** 我们此前只发布
`document.md`，所以引用后面没有东西，必然裂。

## 决策

### D1 — 图片与 markdown 同级放置，markdown 保持逐字节原样

markdown 写的是裸文件名，那么图片 artifact 的 `relative_path` 就用**同一个裸文件
名**，与 `document.md` 同目录。这样：

* 存储的 markdown 与 Datalab 的产出完全一致（D9a 已定：不把绝对 URL 烧进文档，
  否则记录被绑死在某个部署域名上，也更容易泄露）；
* 渲染时用 `relative_path → artifact_id` 精确匹配即可解析，不需要猜路径。

### D2 — 落盘范围：返回的都存，不按引用裁剪

那 1 张没被引用的图片也存。它是这次付费转换的产物，丢掉不可逆；保留它只是多几
百 KiB。代价是存在"有 artifact 但没人引用"的文件，可接受。

### D3 — 上限用"数量 + 总字节"，不设最小尺寸阈值

* `DOCUMENT_MAX_IMAGE_ARTIFACTS`（默认 **200**）
* `DOCUMENT_MAX_IMAGE_BYTES`（默认 **32 MiB**）

provider 按 markdown 引用顺序优先保留（被引用的优先），超出上限的**丢弃并在主
artifact 的 metadata 里记账**（`images_kept` / `images_dropped` / `image_bytes`）
外加一条 `warning`。理由：宁可少存几张并如实告知，也不要让一个超大扫描件把整
个任务判失败——那是 D9a 点名的风险，`max_artifacts`(256) 与 50 MiB 的
`max_bundle_bytes` 原本就会这么干。

不设"小于 N 字节就丢"的启发式：一个 800 字节的小图也可能是正文的一部分，这条
规则我无法给出可辩护的边界。

### D4 — 执行器把图片从 markdown 的字节预算里拿出来

`_validate_bundle` 原本把 bundle 内所有文件字节加总比对 `max_bundle_bytes`
（默认 = 50 MiB 上传上限）。图片计入这个预算，就会出现"文本明明很小、却因为图
片而失败"。改为：普通 artifact 计入 `max_bundle_bytes`，`embedded_image` 计入
`max_image_bytes`，两个上限各自报错，消息可区分。这是一道**兜底**（provider 已
经按 D3 限过），防的是别的 provider 或未来改动。

### D5 — 预览在渲染时解析相对引用（前端）

`DocumentPreviewDrawer` 已经拉取了该文档的 artifact 列表，所以可在渲染前把
`![alt](name.jpg)` 里能匹配到 artifact 的引用改写成
`${origin}/api/v1/document-artifacts/{artifact_id}/download`。

* **必须带 origin（绝对 URL）**：共享的 `Markdown` 组件把**非外部** `src` 交给
  `WorkspaceImage`，而后者走的是**工作区**文件下载接口——文档 artifact 不在工作
  区里，相对路径过去必然 404。带 origin 的绝对 URL 会被判为 external，直接由浏
  览器以同源 cookie 拉取，正好走我们那个带 owner 校验的接口。
* 已经是绝对 URL / `data:` / `blob:` 的引用原样不动。
* 匹配不到的引用原样保留：今天就是这个行为（alt 文字还在），不做静默删除。

### D6 — 绝不使用公开桶地址

这些是家庭文档（常是孩子的扫描作业）。图片只能经
`/api/v1/document-artifacts/{artifact_id}/download` 读取，`media_type` 按图片真实
类型发送，这样 `<img>` 能正常渲染。

### D7 — 提取默认改为开

D9 把默认设成关的**唯一理由**是"存了也没法显示"。这条理由现在消失了，所以：

* `DatalabConversionOptions.disable_image_extraction` 默认改为 `False`；
* 向导里"提取图片"复选框默认勾选，提示文案改为说明图片会作为独立文件保存并在
  预览中显示；
* `disable_image_captions` 仍默认 `True`（不生成图片标题）——那是另一件事：标题
  会跟正文抢精度。

## 风险

* **成本与体积**：图片会增加每份文档的存储量，也会让 Datalab 多做提取工作。
  上限（D3）挡住最坏情况，且开关仍然对用户可见。
* **文件名不可信**：SDK 给的 key 来自服务端，理论上可能带路径分隔符。落盘前统一
  取 basename、拒绝空/`.`/`..`，并做去重，避免写到 bundle 目录之外。
* **未引用图片**：保留（D2）意味着 artifact 列表里会有预览用不到的文件，属已知
  取舍。

## 不在本次范围

* 图片的富交互（灯箱、图库、按页浏览）。
* 未解析文档的孤儿清理（这是上传/取消路径的问题，与本次无关）。

## 实测（2026-09-15，`RE3 Part.pdf` 2.98 MB / 5 页）

走真实 API：上传 → 检测 → `datalab-online` → 解析 → 取 artifact。

| 观测 | 值 |
|---|---|
| 任务耗时 | 冷跑 247 s（同一文件第二次走缓存仅 16 s） |
| 图片 artifact | **7** 个，合计 754 497 B，`images_dropped=0` |
| markdown | 14 994 字符，**6** 处图片引用，全部能在 artifact 列表里找到对应 `relative_path` |
| 存储 key | `documents/doc-kEdIsxVKorxP/artifacts/job-EBaWM1Ay5RFh/<32位hex>_img.jpg`（与 `document.md` 同目录） |
| 下载 | `/api/v1/document-artifacts/{id}/download` → 200，`Content-Type: image/jpeg` |
| 预览 | 浏览器实测 6 个 `<img>` 全部加载成功（naturalWidth/Height 非 0），截图见本次会话 |
| 费用 | 2 分（缓存命中记 0） |

### 两个与预期不符、必须记下来的事实

1. **图片数量在同样的选项下会变**。同一个文件、同样 `options`（`captions` 关、
   提取开）跑了两次冷转换：一次得到 **2 张图 / 1 处引用**，另一次得到
   **7 张图 / 6 处引用**。所以"这一轮有几张图"**不是我们能控制的**，实现必须容忍
   任意子集——这也是为什么预览对匹配不到的引用**原样保留**而不是删除，以及
   provider 对返回什么就存什么（不做"必须有 N 张"的假设）。
2. **`disable_image_captions` 影响的是 alt 文字，不是数量**。关掉标题时引用形如
   `![](<hex>_img.jpg)`（alt 为空），打开时形如
   `![A photograph of a ski resort …](<hex>_img.jpg)`。我一开始从一次运行得出
   "关标题会连带丢图"的结论，第二次同配置冷跑就直接推翻了这个结论——记在这里，
   免得后来者照着那个错误结论做优化。
