# 验证记录

验证日期：2026-11-10。版本：0.1.0。

## 已完成

- 本地 Python 3.12.14 / macOS arm64 环境，80 项自动化测试全部通过。
- 实时读取 IP233 公开模型元数据：33 个型号，其中 27 个具有结构化参数及端点；这些型号的默认请求参数均通过本地校验。只进行了元数据 GET，没有提交付费生成。
- 验证根节点映射能在不同安装目录名下发现 12 个节点，导入阶段没有联网。
- 验证 IMAGE / MASK 的形状、透明通道、完整批次、GIF 帧保留和原文件保存。
- 使用真实 tensor / Pillow 转换，模拟 HTTP 验证本地图片 multipart 编辑和 Gemini Data URI 编辑。
- 模拟 API → CDN 重定向，验证 API Key 不转发给外部下载域名；验证 HTTPS 默认校验、下载限额及临时文件清理。
- 验证收费 POST 只发送一次、任务日志不包含配置中的 API Key、原 ID 轮询及跨 API 地址保护。
- 生成 4 份画布工作流和 4 份 API prompt；验证连线一致，示例不含 Key。
- 使用官方当前 custom-node-list.json 验证仅插入新增条目，原有文本不重排。未写入官方仓库或创建 PR。
- 验证源码 ZIP 排除本地凭据、环境文件和缓存。
- 本地开发包构建成功。ComfyUI 安装应使用完整源码目录或源码 ZIP。
- 发布前置检查正确阻止缺少真实 Repository / PublisherId 的配置。
- 已创建公开 GitHub 仓库并绑定 Repository 元数据；尚未提交官方收录申请。
- 修复 Manager 大文件读取：按不可变 Git blob SHA 读取并校验官方当前清单，避免 Contents API 的大文件空响应及移动分支竞态。

## 尚待完成

- 使用实际 ComfyUI 版本和测试 API Key，完成图片生成、透明背景、参考图编辑、视频生成及中断恢复验收。
- 实测 /media/uploads 对当前 Key 的返回字段；若只返回 token，继续使用受支持的本地编辑输入或 HTTPS 素材地址。
- 原生 VideoFromFile 的字符串路径构造方式已按官方源码核对；本地测试使用替身验证调用约定，未运行完整 ComfyUI / 视频编解码环境。
- CI 已配置 Python 3.10 / 3.12，支持手动启动；远端验证状态以仓库 Actions 的实际结果为准。
- 确认 Registry 发布者身份并配置 Registry 发布凭据。
- 正式提交 Registry / Manager 收录申请，并记录实际版本状态或 PR URL。

以上未完成项不能用自动化测试通过替代，也不能被描述成已经上线、已官方审核或已被 Manager 收录。
