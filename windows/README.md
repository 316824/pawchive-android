# Pawchive Downloader · Windows 版

用于下载 Pawchive 画师主页下图集原图与帖子附件的 Windows 桌面工具。界面使用 PySide6，支持封面预选、按图集整理文件，以及明暗主题和多语言切换。

## 下载与运行

前往 [Windows v1.0.1 发布页](https://github.com/316824/Pawchive-Downloader/releases/tag/windows-v1.0.1)，优先下载 Windows 便携 ZIP，解压后双击 `PawchiveDownloader.exe` 即可运行。发布页也提供单独的 EXE 文件。

发布的 EXE 面向 **64 位 Windows**，已包含 Python 运行环境和依赖库，无需另外安装 Python 或 PySide6。分享便携包时，请保留包内的许可证和第三方依赖说明。源码运行与打包方法见下文。

## 版本说明与已知问题

**v1.0.1 针对 v1.0.0 的 QtCore 启动失败重新构建。** 旧版本可能在显示主界面前报错：

```text
ImportError: DLL load failed while importing QtCore: 找不到指定的程序。
```

已在 Windows 11 上重现旧包故障，并通过二进制依赖核查确认：旧包误收了一份第三方 ICU 78 动态库，其导出的函数名称与 QtCore 所需的 Windows 系统 ICU 接口不匹配。本次打包配置排除这类系统 ICU 同名文件，使用 Windows 自带实现，同时隔离构建工具的搜索路径，检查内嵌依赖并对生成的 EXE 执行离线自检。

普通用户只需重新下载 v1.0.1。请勿向程序目录随意复制其他软件的 Qt 或 ICU DLL。具体执行过的检查和系统范围以 [本次发布说明](https://github.com/316824/Pawchive-Downloader/releases/tag/windows-v1.0.1) 为准；离线启动检查不能替代所有 Windows 版本上的兼容性测试，也不代表网站下载服务始终可用。

Android 使用另一套平台原生库，Windows 的 DLL 修复不等于修复 Android 启动兼容性。此前 Android 12 设备闪退、Android 13～15 未验证的状态仍保留，详见 [Android 兼容性说明](../docs/ANDROID.md#设备要求与兼容性)。

## 快速开始

1. 输入完整的画师主页链接，例如 `https://pawchive.pw/fanbox/user/76050360`。
2. 点击“浏览…”选择保存文件夹；按需勾选“保存为默认路径”。
3. 选择日期顺序和保存方式，点击“开始下载”。
4. 默认先扫描图集。在选择窗口中检查封面、标题和附件类型，取消不需要的图集，然后确认下载。
5. 等待下载结束，点击状态文字右侧的“打开文件夹”查看文件。

“开始下载”会在主页链接有效且已选择保存位置后启用。需要填写画师主页链接，不能填写单个帖子链接。程序会按网站的分页规则继续读取后续图集。

## 扫描与选择

- “先扫描标题并选择下载图集”默认开启；关闭后直接下载主页下找到的全部图集。
- 图集默认全部选中。点击封面卡片或卡片上的复选框可逐个调整，彩色边框表示已选中。
- 卡片会显示帖子中直链附件的格式提示，例如 ZIP、MP4、PSD；也提供全选、全不选和回到顶部按钮。
- 扫描窗口支持暂停、继续和结束扫描。“结束扫描”会在当前处理结束后，返回已完整收集到的图集供选择。

## 保存规则

| 选项 | 行为 |
| --- | --- |
| 日期顺序 | 可选择从新到旧或从旧到新下载 |
| 按图集标题分别存入文件夹 | 默认开启，按帖子标题创建子文件夹 |
| 下载后按日期顺序编号重命名 | 关闭图集文件夹后可用；将本次下载的文件按发布日期从旧到新编号，并保留扩展名 |
| 起始编号 | 默认从 `1` 开始，可自行调整 |
| 保存为默认路径 | 默认关闭；开启后将当前保存位置记在本机，下次启动时使用 |

图片原图和页面提供的直链附件会一并下载。重名文件会添加序号；平铺保存时，部分跨图集的同名直链附件会加上图集标题以便区分。

下载期间会显示当前文件的进度、已接收大小和图集序号。程序会对常见无效响应进行检查，遇到临时失败会重试；ZIP、MP4、PSD 等直链文件之间会适当等待。

如果任务新建的图集文件夹下载不完整，程序会清理该未完成的文件夹。已有目录不会被整目录删除，此前已经完成的其他图集会保留。关闭窗口时，程序会先请求停止任务，待任务退出后再关闭窗口和清理临时缓存。

## 外观与辅助功能

- 简体中文、繁體中文、English 和日本語界面。
- 太阳／月亮滑钮切换明暗主题。
- 鼠标粒子、按钮高亮、复选框渐变动画和彩虹进度条。
- 日志一键复制，下载完成后一键打开保存文件夹。
- 顶部扫帚按钮清理空闲时的临时缓存；工作期间会禁用，避免影响正在使用的封面和任务。
- 底部彩色署名带有悬停加速、单字弹动和点击烟花效果。

缓存用于封面预览，与用户选择的下载文件夹分开保存。正常关闭程序时会清理该次运行的临时缓存。

## 从源码运行

先安装所选 PySide6 版本支持的 **64 位 Python**。本次 Windows 构建使用 Python 3.14；其他 Python 版本需自行验证。在仓库根目录打开 PowerShell，然后执行：

```powershell
cd windows
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe download_pawchive_images.py
```

`requirements.txt` 固定直接运行依赖：`PySide6-Essentials==6.12.0`、`requests==2.34.2`、`beautifulsoup4==4.15.0`。PySide6-Essentials 提供本程序使用的 `PySide6` 核心与界面模块，无需额外安装完整 Addons、WebEngine 或 PDF 组件。更新依赖后应重新检查界面、文件处理和下载行为。

请将 `1.ico` 与脚本放在同一目录，程序会使用它作为窗口图标。

## 自行打包 EXE

在干净的 Windows 虚拟环境中构建。在仓库根目录打开 PowerShell，然后执行：

```powershell
cd windows
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-build.txt
.\.venv\Scripts\python.exe build_release.py
```

`requirements-build.txt` 包含运行依赖及固定的 PyInstaller、构建 hooks 和 PE 文件检查工具。`build_release.py` 配合仓库中的 `PawchiveDownloader.spec`：

- 使用最小化的构建搜索路径，避免收入其他软件目录中的同名动态库。
- 只收集实际使用的 Qt 模块、必要插件和运行依赖，并打包 `1.ico`，保留程序与窗口图标。
- 核查 ICU 和内嵌二进制依赖，执行生成 EXE 的离线启动自检；失败时停止构建流程。

成功后文件位于 `dist/PawchiveDownloader.exe`。请使用上述构建入口，不建议直接复制旧版通用 `--onefile` 命令跳过依赖检查。源码中的 `.spec` 是可审阅的构建配置；用户运行发布 EXE 时不需要它或 `build` 目录。

固定依赖和构建配置用于减少环境差异，不保证不同系统或工具环境生成逐字节相同的 EXE。发布与分享时仍须保留 MIT 许可和第三方依赖说明。

## 使用范围与问题反馈

程序需要能够访问 Pawchive 及其文件服务器。网站页面结构、链接有效性或访问限制发生变化时，可能需要调整解析与下载逻辑；文件类型检查也不等同于完整内容校验。

遇到问题时，可使用日志复制按钮整理错误信息，在 [Issues](https://github.com/316824/Pawchive-Downloader/issues) 中说明系统环境、操作步骤和实际结果。提交前请移除日志中的私人路径或不希望公开的信息。

本项目为非官方工具。请只保存你有权下载的内容，遵守服务规则和版权要求。项目自有代码适用根目录的 [MIT License](../LICENSE)，第三方依赖分别适用其各自许可证。

千泽音奈 · QQ：3412892533
