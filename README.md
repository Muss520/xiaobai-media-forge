# 小白媒体工坊

![小白媒体工坊](assets/xiaobai-logo.png)

面向 Windows 10/11 x64 的离线媒体工具，提供图片、视频与 Live Photo 处理，以及可以拖入文件的桌面小白。

## 下载与启动

前往 [Releases 下载页](https://github.com/Muss520/xiaobai-media-forge/releases/latest)，下载 `小白媒体工坊-Windows-x64.zip`，解压后双击 `MediaForge/小白媒体工坊.exe`。

请保留完整 MediaForge 文件夹，不能只复制 EXE。免安装版内置所需引擎，日常使用不需要安装 Python 或 FFmpeg，也不需要联网。

下载页附带 `.sha256` 文件，可用 PowerShell 检查 ZIP 的 SHA256：

```powershell
Get-FileHash -LiteralPath '.\小白媒体工坊-Windows-x64.zip' -Algorithm SHA256
```

关闭主窗口后，任务继续在后台运行。右键小白或托盘，选择“彻底退出”结束软件。

## 功能

- 小白模式提供添加文件、选择需求、查看结果三步流程；专业模式可调整详细参数。
- 图片和视频格式转换、尺寸与质量控制，以及 Live Photo 配对和导出。
- 媒体信息查看与编辑；处理结果使用新文件，保留原件。
- 拖文件给桌面小白可创建处理任务，后台任务支持进度、取消与结果查看。
- 3.8 新增摸头、蹭蹭、喂零食、叫一声，以及逗猫棒和 30 秒抛接小球。
- 设置提供总音量、转换/宠物/游戏分类音量，以及猫叫、待机反应和小游戏开关。

完整操作说明见 [使用说明](docs/使用说明.txt)。

## 开发与构建

使用 **Windows x64、Python 3.12 和 PowerShell**。仓库采用独立源码布局：`src` 为应用代码，`assets` 为素材，`tests` 为测试，`scripts` 为构建与验证辅助脚本，`docs` 为说明和许可。

### 准备依赖和引擎

1. 安装 Python 3.12，并确认 `py -3.12` 可运行。
2. 下载对应版本的免安装包，解压到仓库外。
3. 在仓库根目录执行以下命令，将发布包中的引擎复制到 `tools`。将示例路径替换为实际的解压路径。

```powershell
$portableFolder = 'D:\Downloads\MediaForge'
Copy-Item -Path (Join-Path $portableFolder '_internal\tools\*') -Destination '.\tools' -Recurse -Force
py -3.12 -m venv .venv
& '.\.venv\Scripts\python.exe' -m pip install -r requirements.lock.txt -r requirements-dev.lock.txt
```

仓库保留引擎版本与校验清单，运行环境和大型引擎文件不提交到 Git。字体和软件使用的图片、音效及打赏素材已包含在 `assets`。`requirements-dev.lock.txt` 中的二维码验证库仅用于开发测试。

### 测试与运行源码

```powershell
& '.\.venv\Scripts\python.exe' -m pytest -q
$env:PYTHONPATH = (Join-Path (Get-Location) 'src')
& '.\.venv\Scripts\python.exe' '.\src\main.py'
```

测试默认使用 Qt 离屏平台。运行应用时若曾手动设置 `QT_QPA_PLATFORM=offscreen`，请先移除该环境变量。

### 构建免安装版

```powershell
& '.\build.ps1'
```

构建脚本先运行测试，再打包。独立源码布局下，程序输出到 `成品/MediaForge`，ZIP 和校验文件输出到仓库根目录。构建需要完整开发依赖；缺失引擎时，脚本会尝试下载并校验清单中的版本。为避免上游下载地址更新后与固定校验值不符，建议使用对应 Release 内的引擎。

## 测试素材与发布整理

公开版本的 Live Photo 测试配对使用程序生成的彩色测试画面和正弦波声音，仅保留配对标识和通用关键帧标记，不包含私人照片、录音或 GPS 信息。它验证软件处理流程，不代表经过 iPhone 实机兼容性认证。

公开仓库和下载包排除了个人配置、日志、已有输出、本机验收报告和依赖私人路径的历史验收脚本。应用源码和程序二进制保持 3.8.0 原版；预览样例配置使用相对输出路径。

## 作者与许可

作者：沐 · 联系邮箱：2504542766@QQ.COM。

软件内“作者与打赏”提供自愿打赏入口，不影响功能。仓库保留软件实际使用的打赏素材。

项目沿用原有 [GNU GPL v3 许可](LICENSE)，第三方许可位于 [docs/licenses](docs/licenses)。
