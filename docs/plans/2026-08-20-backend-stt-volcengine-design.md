# 火山引擎后端语音识别设计

## 背景与目标

当前聊天输入框依赖浏览器 Web Speech API 进行语音转文字。目标是增加火山引擎豆包语音“一句话识别”的后端流式识别能力，并将其作为默认路径：

- 浏览器录音期间持续发送音频包；
- 音频固定为 16 kHz、16-bit、单声道 raw PCM；
- 火山引擎凭据只存在 Python 后端，浏览器永远不接触 `appid`、token 或 secret；
- 保留现有录音动画、实时文本填充和用户语音输入开关；
- 录音中的麦克风图标改为 Lucide `Square`；
- 后端路径不可用时保留现有浏览器 Web Speech API 作为降级方案。

火山协议依据官方“一句话识别”文档：
<https://docs.volcengine.com/docs/6561/80816?lang=zh>

## 方案选择

### 采用：同一 FastAPI 应用内的 WebSocket 中转

增加一个受 Cookie 保护的 WebSocket 路由 `/ws/v1/speech/transcribe`。后端接收浏览器 PCM 帧，同时以火山二进制协议连接上游 WSS，双向转发并转换识别事件。

这个方案复用现有 `authenticate_websocket`、FastAPI 生命周期、部署入口和 Vite `/ws/v1` 代理，不需要新增进程、端口、数据库表、BYOK 记录或专用 REST API。火山凭据属于部署级默认服务凭据，不属于用户模型 BYOK，因此不接入 LLM Endpoint/BYOK 数据库架构。

### 不采用：独立 ASR 进程

独立端口可以隔离故障，但会引入额外进程管理、反向代理、Cookie/CORS、健康检查和部署配置。现有服务没有必须隔离 ASR 的资源边界，收益不足以抵消运维复杂度。

### 不采用：浏览器直连火山

浏览器直连需要暴露 token 或签名材料，违反密钥不出后端的安全要求。

## 配置与凭据

在 `src/config/env.py` 定义环境变量常量，在 `src/config/settings.py` 提供类型化访问器，不在业务路由中散落 `os.getenv`。`.env.example` 增加无值占位：

- `VOLCENGINE_ASR_APP_ID`
- `VOLCENGINE_ASR_ACCESS_TOKEN`
- `VOLCENGINE_ASR_ACCESS_SECRET`
- `VOLCENGINE_ASR_CLUSTER`
- 可选的 `VOLCENGINE_ASR_WS_URL`（默认官方 WSS 地址）

配置访问器返回完整配置或“未配置”状态。配置了 `access_secret` 时使用官方 HMAC256 WebSocket 签名鉴权；未配置 secret 时允许使用官方 Bearer token 鉴权，以支持简单部署。缺少必要的 app id、token 或 cluster 时，WebSocket 返回固定的服务不可用错误。

本机 `temp_pwd.txt` 仅用于运维人员将值注入运行环境。它不是应用配置文件，不会被复制到 worktree、加入代码、写入日志或提交；测试只使用虚构凭据。

## 数据流与协议

### 浏览器到 LangAlpha

1. 用户点击麦克风按钮，前端创建同源 WebSocket，并发送 JSON `start` 控制帧（包含语言和请求标识，不含任何供应商凭据）。
2. 前端调用 `getUserMedia`，通过 Web Audio 将输入转换为 16 kHz、16-bit、单声道 little-endian PCM。
3. 前端累计约 100 ms 音频（约 1600 samples / 3200 bytes）后发送一个二进制帧。控制帧只能是已知的 `start`、`stop`。
4. 用户停止录音时发送 `stop`，然后释放媒体轨道、AudioContext 和浏览器 WebSocket。

### LangAlpha 到火山

1. 后端完成 Cookie 鉴权和配置校验后建立火山 WSS。
2. 后端发送 full client request：`raw`、`rate=16000`、`bits=16`、`channel=1`，并启用 `show_utterances=true`、`result_type=single` 以获得中间分句。
3. 后端将每个 PCM 包封装为火山 audio-only request，sequence 从 1 递增；最后一包使用相反数表示结束。
4. 后端解压并解析火山 full server response，将 `definite=false` 映射为 `partial`，`definite=true` 映射为 `final`。
5. 浏览器只收到内部事件格式：

   - `partial`: 当前临时文本；
   - `final`: 已确认文本；
   - `error`: 固定的内部错误类型；
   - `done`: 识别流正常结束。

上游协议错误、鉴权错误和供应商响应原文不会下发到浏览器。

## 前端交互与降级

将 `useVoiceInput` 改为后端优先的双路径实现：

- 默认路径使用 WebSocket + Web Audio PCM 采集；
- 浏览器不支持必要的 WebSocket/媒体采集能力，或后端连接在识别启动阶段失败时，启动现有 Web Speech API；
- 已生成的文本保留，降级识别继续追加到同一 composer；
- 权限拒绝沿用现有 `permissionDenied` 提示；后端服务失败使用现有 `serviceError` 提示；
- 录音动画、`recording` class、waveform 和 `Listening...` 文案保持不变；
- 录音状态按钮渲染 `Square`，停止动作和 `aria-label` 继续使用现有翻译键；
- 麦克风入口显示条件为后端采集能力或浏览器 SpeechRecognition 至少一项可用，并继续受 `voice_input_enabled` 控制。

音频转换优先使用 AudioWorklet；对不支持 AudioWorklet 的浏览器使用兼容的 ScriptProcessor 采集，均在前端完成 float32 到 PCM16 的转换。每次停止或失败都要停止所有 MediaStream tracks，避免占用麦克风。

## 错误、安全与资源边界

- 不记录凭据、Authorization header、原始音频或完整上游错误文本；日志最多包含脱敏阶段和错误码。
- WebSocket 握手缺少或无效 session cookie 时以 `1008` 关闭。
- 客户端消息类型、单包大小、总连接时长和空闲等待均受限；未知控制帧立即以协议错误关闭。
- 任一端断连、取消、超时或上游失败时关闭另一端，并在 `finally` 中释放上游连接和任务。
- 缺少部署配置不影响聊天主链路，只让本次语音连接进入浏览器降级或显示统一服务错误。

## 测试与验证

### 后端

- 配置读取、空配置和环境变量别名；
- Bearer/HMAC256 鉴权头生成（使用虚构值）；
- 火山二进制 header、gzip payload 和 response 解码；
- sequence 递增与最后包标记；
- partial/final/done/error 事件转换；
- WebSocket Cookie 鉴权、断连清理、超时和错误脱敏；
- 路由注册不影响现有通用 API。

### 前端

- PCM16 转换与 100 ms 分包；
- 后端路径优先、partial/final 文本合并；
- WebSocket/媒体能力缺失和启动失败时切换 Web Speech；
- 停止时释放音频资源和连接；
- `Square` 停止图标和可访问标签。

验证只使用 mock WebSocket、虚构配置和测试音频，不调用真实火山服务。完成后运行后端聚焦单测、前端 `pnpm typecheck`、相关 Vitest，并按项目要求启动 `0.0.0.0:5177` 做浏览器可达性检查。
