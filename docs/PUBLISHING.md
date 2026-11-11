# 发布到 Comfy Registry 与 Manager

**准备完成不等于已收录。** 已创建公开仓库 https://github.com/liuhang01/ComfyUI-IP233-API ，并绑定到项目元数据。Registry PublisherId 尚未配置，Registry 发布检查会因此阻止误发；Manager 列表 PR 可以单独办理。

官方依据：

- https://docs.comfy.org/registry/publishing
- https://docs.comfy.org/registry/specifications
- https://github.com/Comfy-Org/ComfyUI-Manager 的 How to register your custom node 小节

## 先验收，再公开

使用专门的测试 API Key，在实际 ComfyUI 中至少验收：文生图、透明背景、参考图编辑、一个视频型号、任务中断恢复，以及 /media/uploads 的 URL 返回格式。运行生成任务可能产生费用。当前自动化测试不会代替这些验证。

检查 LICENSE、README、requirements、静态节点映射和示例；确保 ip233.local.json、.env、真实 API Key、临时结果 URL 及用户素材不进入 Git 仓库。

建议仓库名 ComfyUI-IP233-API。Registry 项目唯一 ID 为 ip233-ai-nodes，显示名称为 IP233 Image and Video，首版版本为 0.1.0。PublisherId 必须使用自己在 Registry 注册的 ID，不可复用参考仓库发布者。

## Comfy Registry

1. 在自己的 GitHub 账号创建公开仓库并上传本项目。
2. 登录 https://registry.comfy.org/ ，创建或选择自己的 Publisher，记下真实 PublisherId。
3. 安装开发依赖后，执行 tools/prepare_release.py，参数 --repository 传真实仓库 URL，--publisher 传注册的 PublisherId。脚本验证仓库公开可访问，再写入 pyproject.toml，并生成 .release/manager-entry.json。
4. 执行 python tools/check_release.py。缺少真实仓库或发布者时会退出失败。
5. 将最终文件提交并推送到仓库；Registry API Key 仅保存在本机环境变量或 GitHub Actions Secret。

命令行发布：

```sh
python -m pip install comfy-cli
comfy --skip-prompt --no-enable-telemetry node publish
```

发布命令在项目根目录执行，并事先在本地设置 COMFY_REGISTRY_TOKEN。不要把 Key 写进命令行参数、README 或聊天记录。Registry 返回结果和版本状态才是实际提交的依据；通过审核和同步后，用户才能在对应 Manager 频道搜索安装。

GitHub Actions 方案：将 Registry Key 存为仓库 Secret REGISTRY_ACCESS_TOKEN，然后手动运行 Publish to Comfy Registry。工作流只允许手动触发，先检查发布身份，再调用官方 comfy-org/publish-node-action。每次新版本须修改版本号并重新验证。

本目录安装到 custom_nodes 时可改名；Python 导入不依赖目录名。pyproject 的包 ID 不带 ComfyUI 前缀，避免与注册规范冲突。

## Manager 列表 PR

Registry 是主要路径；仍可向官方 Manager 的 custom-node-list.json 提交条目。无需手改生成的节点映射文件。

准备脚本：

```sh
python tools/submit_manager.py
```

如果暂不使用 Comfy Registry，prepare_release.py 只传 --repository 即可生成 Manager 条目，不必先注册 Publisher。此时 Registry 专用的 check_release.py 仍会因缺少 PublisherId 而失败，符合预期。

默认只输出待提交条目，不产生外部写入。绑定仓库后，可在本地设置 GITHUB_TOKEN，再执行：

```sh
python tools/submit_manager.py --submit
```

此操作会在认证 GitHub 账号下 fork 官方 Manager、创建独立分支、添加条目并提交真实 PR。Token 需有相应仓库及 PR 权限。脚本不自动重试写入，也不会覆盖现有分支；如中断，请先检查已存在的 fork、分支和 PR 再继续。脚本输出 PR URL 后，交由官方维护者审核。

脚本不会把 API Key 放进条目。描述明确提示需要 IP233 Key 和付费服务。收到实际 PR URL 才能称为已报送；PR 合并和 Registry 审核通过之前，不能承诺已收录或立即可搜索。

## 提交文案

标题：Add IP233 Image and Video nodes

正文：

Registers an MIT-licensed custom node pack for IP233 Media API. Provides image generation/editing, video generation, native IMAGE/MASK/VIDEO outputs, and task recovery. Requires an IP233 API key and paid service usage. Dependencies are declared in requirements.txt and pyproject.toml. Uses static NODE_CLASS_MAPPINGS, no import-time network calls, no runtime package installation, and no embedded credentials.

项目仓库地址由准备脚本填入实际提交内容，不使用假账号、假 PublisherId 或不存在的仓库。
