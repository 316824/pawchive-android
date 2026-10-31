# Pawchive Downloader

<p align="center">
  <img src="assets/app_icon.png" alt="Pawchive Downloader icon" width="120">
</p>

用于保存 Pawchive 画师主页中图片原图和帖子附件的开源工具，提供 **Windows 桌面版**和 **Android 版**。可先扫描封面与标题，选择需要的图集，再按日期和标题整理下载文件。

## 选择你的版本

| 平台 | 下载与使用 | 源码与构建说明 |
| --- | --- | --- |
| Windows 64 位 | [下载 Windows 版 EXE / ZIP](https://github.com/316824/pawchive-android/releases/tag/windows-v1.0.0)，无需安装 Python | [Windows 版说明](windows/README.md) |
| Android ARM64 | 在 [Actions](https://github.com/316824/pawchive-android/actions/workflows/build-android.yml) 下载最近一次成功构建的 APK，下载 Artifact 需要登录 GitHub | [Android 版说明](docs/ANDROID.md) |

Windows 用户推荐下载 `PawchiveDownloader-Windows-x64.zip`，解压后双击 `PawchiveDownloader.exe`。ZIP 同时附带使用说明、MIT 许可证和第三方许可文件；也提供与本次发布对应的单独 EXE。

## 主要功能

- 输入完整画师主页链接，自动读取分页中的图集。
- 预览封面、标题和直链附件类型，逐个选择需要下载的图集。
- 支持新到旧、旧到新排序，以及扫描的暂停、继续与提前结束。
- 保存图片原图和页面直接提供的附件，如 ZIP、MP4、PSD 等。
- 按图集标题创建文件夹，或平铺保存并按日期编号。
- 显示下载进度和日志，处理临时连接失败与文件重名。

Windows 版还提供明暗主题、四种界面语言、鼠标粒子效果、彩虹进度条、日志复制、缓存清理和下载后打开文件夹等桌面功能。两个版本的界面与实现不同，具体选项请参考各自说明。

## Windows 快速开始

1. 从 [Windows Release](https://github.com/316824/pawchive-android/releases/tag/windows-v1.0.0) 下载并解压 ZIP。
2. 双击 `PawchiveDownloader.exe`。
3. 输入完整的画师主页地址，例如 `https://pawchive.pw/fanbox/user/76050360`。
4. 选择保存文件夹，设置排序和保存方式，点击开始下载。
5. 默认先扫描并打开封面选择窗口；确认所选图集后继续下载。

程序需要能够连接 Pawchive 及其附件服务器。请输入画师主页链接，单篇帖子链接不适用于主页扫描入口。网站响应或页面结构变化可能影响扫描与下载，遇到问题时可在 Issue 中提供去除个人信息后的错误日志。

## 从源码运行与构建

- **Windows**：进入 `windows` 目录，按 [Windows README](windows/README.md) 安装依赖、运行脚本或使用 PyInstaller 打包。
- **Android**：保留仓库根目录的 `main.py` 作为移动版入口，使用 GitHub Actions 构建。签名密钥配置、APK 安装与构建环境见 [Android README](docs/ANDROID.md)。

```text
.
├── windows/
│   ├── download_pawchive_images.py   # Windows 桌面版
│   ├── 1.ico                        # 桌面版图标
│   ├── requirements.txt
│   └── README.md
├── docs/ANDROID.md                  # Android 使用和签名说明
├── main.py                          # Android 版入口
├── assets/app_icon.png              # Android 图标
├── scripts/                         # Android 构建配置辅助脚本
├── .github/workflows/               # Android 云端构建工作流
└── LICENSE
```

签名密钥、密码、个人设置、下载内容和本地备份不应提交到仓库。Android 工作流通过 GitHub Actions Secrets 读取发布密钥；Fork 仓库的维护者需要配置自己的密钥。

## 许可与贡献

本项目原创代码以 [MIT License](LICENSE) 发布。Python、PySide6 / Qt、Requests、Beautiful Soup、PyInstaller 等第三方组件遵循各自许可证；Windows ZIP 中附有第三方许可文本，MIT 许可不会替代它们。

欢迎通过 Issue 反馈问题，或通过 Pull Request 改进代码、文档和翻译。提交问题时请注明平台、程序版本、错误信息和复现步骤，并避免附带密码、密钥或私人下载内容。

本项目为非官方工具，与 Pawchive、Pixiv、Fanbox 及其他相关服务没有隶属或认可关系。请只保存你有权下载的内容，并遵守网站规则和相关版权要求。

## English

Pawchive Downloader is an unofficial open-source tool for Windows and Android. It scans creator pages, previews posts, and saves selected images and direct-link attachments. Download the Windows executable from [Releases](https://github.com/316824/pawchive-android/releases/tag/windows-v1.0.0), or see the [Android guide](docs/ANDROID.md) for APK builds. The project's original code is MIT-licensed; third-party dependencies retain their own licenses. Download only content you are authorized to save.
