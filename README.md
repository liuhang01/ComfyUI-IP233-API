# IP233 Image and Video for ComfyUI

IP233 图片与视频模型节点合集，独立参考 ComfyUI-Tikpan-Pro 的接入方式实现。服务网站：https://new.ip233.com/ 。

支持图片生成、参考图编辑、透明背景、GIF、视频任务、任务恢复和原生 IMAGE / MASK / VIDEO 输出。模型菜单来自公开模型文档；每次生成前重新读取当前合同、校验参数，并在合同提供版本时发送 X-IP233-Contract-Version。

**当前为待实机验收的 0.1.0 首版，尚未获 Comfy Registry / Manager 收录。** 本地自动化测试不等于真实付费模型实测。需要站点 API Key、账户余额以及对应模型权限；请求可能收费，审核拒绝等规则以站点说明为准。

项目仓库：https://github.com/liuhang01/ComfyUI-IP233-API 。

## 安装

使用 Python 3.10+ 的 ComfyUI。原生 VIDEO 输出需要支持 VideoFromFile 的 ComfyUI 版本。下载整份项目，放到：

```text
ComfyUI/custom_nodes/ComfyUI-IP233-API/
```

使用运行 ComfyUI 的同一个 Python 安装依赖并重启：

```sh
python -m pip install -r requirements.txt
```

也可在 ComfyUI 根目录通过 Git 安装：

```sh
git clone https://github.com/liuhang01/ComfyUI-IP233-API.git custom_nodes/ComfyUI-IP233-API
python -m pip install -r custom_nodes/ComfyUI-IP233-API/requirements.txt
```

项目不在导入时联网、不在运行中安装软件，也不附带 API Key。正式收录后可在 Manager 搜索 IP233 Image and Video；**现在不能声称 Manager 已能搜索安装本项目。**

## API Key

推荐启动 ComfyUI 前设置环境变量 IP233_API_KEY，或将 ip233.local.example.json 复制为 ip233.local.json，并在其中填写 api_key。环境变量和本地配置不会成为节点输出或被写入任务日志。

API Config 的 api_key 输入可留空。优先级为：节点输入、环境变量、本地配置。**直接填在节点上的 Key 会保存到工作流，分享工作流前必须清除。** ip233.local.json 和 .env 已被 Git 忽略。不要把 Key 放进截图、GitHub、工作流示例或问题报告。

默认 API 地址为 https://api-new.ip233.com/v1 ，公开参数地址为 https://new.ip233.com/api/pricing 。这与网站首页地址用途不同，依据 2026-11-10 读取的站点文档设置。自定义网关时同时更改这两个地址。HTTPS 证书校验始终开启。

## 节点

| 节点 | 用途 |
| --- | --- |
| IP233 API Config | API 地址、凭据与请求超时，输出配置连接 |
| IP233 Model Info | 拉取最新模型、Key 可访问状态、参数、默认值与参考素材限制 |
| IP233 Image Parameters | 拼接图片参数 JSON，空值沿用模型默认值 |
| IP233 Video Parameters | 设置时长、比例、分辨率与扩展参数 |
| IP233 Image Generate / Edit | 提交一次图片任务，generate 或 edit 模式 |
| IP233 Video Generate | 提交一次视频任务，支持可选防重操作 Key |
| IP233 Resume Task | 输入原任务 ID，恢复 image / edit / video 任务 |
| IP233 Task Status | 查询一次状态，输出响应 JSON |
| IP233 Wait for Task | 可中断轮询，默认最多等待 1800 秒 |
| IP233 Image Result | 自动等待并下载图片，输出 IMAGE、透明 MASK 和文件路径 |
| IP233 Video Result | 自动等待并下载视频，输出原生 VIDEO、本地路径和结果 URL |
| IP233 Upload Reference Images | IMAGE 批次上传；只接受上传结果中的真实 HTTPS 素材 URL |

## 开始使用

将 examples/workflows/ 内的 JSON 拖入 ComfyUI。examples/api/ 内是供程序调用的 API prompt，不是画布工作流。所有示例的 Key 为空。

- image_generate.json：API Config → Image Generate / Edit → Image Result → Save Image。
- image_edit.json：填写自己的 reference_urls，保持 edit 模式。空参考图会在收费请求前报错。
- video_generate.json：API Config → Video Generate → Video Result，视频保存在 output/ip233。
- video_resume.json：填入原任务 ID 后运行，只查原任务，不重新创建。

API Config 的 config 输出同时连接所有需要配置的节点。Video Result 的 VIDEO 也可连接 ComfyUI 原生 Save Video。不要把本地路径 STRING 接到 VIDEO 插口。

图片和视频节点的 parameters_json 默认为空对象，沿用所选型号的公开请求默认值。先用 Model Info 查看该型号合同；不同图片型号可能使用 size、aspect_ratio、quality、resolution 或 image_size，不能套用同一组字段。Image Parameters / Video Parameters 的输出可连接 parameters_json，也可以直接填写 JSON。

### 图片示例参数

GPT Image 2.6 透明背景静态图片：

```json
{"size": "1:1", "background": "transparent", "output_format": "png"}
```

GPT Image 2.6 GIF：

```json
{"size": "1:1", "output_format": "gif", "frame_count": 9, "frame_duration_ms": 200}
```

Gemini 3.1 Flash Image Preview：

```json
{"aspect_ratio": "16:9", "resolution": "1K"}
```

IMAGE 输出为 RGB float32 批次；MASK 为 1-alpha，透明处 1、不透明处 0。原始 PNG/WebP/GIF 保留在 output/ip233。GIF 解为帧批次，播放时长仍以原始 GIF 为准。Save Image 默认不恢复原始 GIF 的播放时序，也不要假定 RGB 输出本身包含 alpha。

图片路由当前一次 n=1。视频秒数、分辨率、参考素材数量及组合按每个型号的结构化参数校验。禁止客户端自填 charge_mode。

### 视频和参考素材

reference_urls 支持每行一个 HTTPS 图片 URL，或 JSON 字符串数组。视频生成会将其映射为 reference_image_urls；图片编辑映射为 images。不得与 parameters_json 中同名参考字段重复填写。

视频参考音频、参考视频可通过 parameters_json 的 reference_videos、reference_audios 数组提交；只对合同允许的型号开放。结构化 references 和其他素材字段不能混用。

本地图片可以从 Load Image 接入 reference_images，设置 edit 模式。只有当前合同明确支持 multipart 或 Data URI 的型号才会接收本地输入：如 GPT Image 2.6 的 multipart 图片，以及 Gemini 的 Data URI；URL-only 型号会在提交前明确报错。本地图片与 reference_urls 不可混用。

也可尝试 Load Image → Upload Reference Images → reference_urls。站点的 /media/uploads 若只返回 upload token，此节点会明确报错，**不会把 token 冒充 URL**。这类模型请使用公开托管的 HTTPS URL。上传接口是否对当前 Key 返回 URL 仍需站长实测确认；本项目未猜测上传 token 的私有解析协议。

## 避免重复提交与恢复任务

生成节点的 request_nonce 是工作流缓存控制值，**不是模型随机种子**。保持不变且其他输入不变时可复用 ComfyUI 内存中的缓存任务；需要有意创建新任务时再更改它。改变输入、清缓存或重启 ComfyUI 后重新运行生成节点仍可能产生新收费请求。

视频创建发送 Idempotency-Key，留空时自动产生并保存到本地日志。相同 Key 代表同一创建操作，不是新视频。图片接口未宣称支持防重，因此绝不自动重试图片 POST。客户端未收到响应也可能已在服务端提交，不要据此直接重新生成。

每次提交前创建 output/ip233/tasks/ 下的 JSON 日志，收到响应后立即记录 task ID。生成节点输出、控制台和日志均可查 ID。日志不保存 API Key 或完整请求提示词，但结果响应可能含临时访问 URL，分享前请脱敏。

中断、网络失败或轮询超时后：查看原任务 ID → Resume Task → Task Status / Wait for Task → 对应 Result。图片生成选 image，图片编辑选 edit，视频选 video，并保持原 API 地址。取消本地轮询不代表取消服务端生成。

## 模型范围和限制

2026-11-10 的公开列表有 33 个型号，其中 27 个有结构化接口文档，可进入生成菜单，覆盖 GPT Image、Gemini / Nano Banana 和当前 Seedance、MiniMax 视频型号。6 个仅列名但无结构化文档的别名不猜测请求方式。服务方补齐文档后，可用 custom_model 填新 ID，提交时会读取最新合同。

菜单快照只用于无联网启动。正式提交必须成功获取当前公开合同；读取失败会停止，不悄悄使用过时计费参数。网络代理、权限、余额和上游模型可用性仍可能导致请求失败。

下载限额：单图片 64 MiB、视频 1 GiB；单图及整个解码批次最多 3200 万像素、最多 64 帧。超出动画解码限额时，可在 output/ip233 使用已保存的原文件。不同大小的图片不会被静默缩放成批次。

## 开发与验证

```sh
python -m pip install -e '.[dev]'
python -m pip install torch
python -m pytest
python tools/build_examples.py
python tools/refresh_catalog.py
```

torch 由正常 ComfyUI 环境提供，未列为节点运行依赖以避免替换用户的 GPU 版本。单独跑测试时需自行安装。所有自动化测试使用模拟 HTTP，不发起付费生成。测试覆盖参数、重定向鉴权隔离、单次收费提交、流式下载、任务持久化、透明 MASK、GIF 帧及安装目录名兼容。

验证范围与待实测项见 docs/VALIDATION.md；发布与报送见 docs/PUBLISHING.md。MIT 许可；致谢与参考版本见 NOTICE。
