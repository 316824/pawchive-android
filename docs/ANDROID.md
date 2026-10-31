# Pawchive Downloader for Android

<p align="center">
  <img src="../assets/app_icon.png" alt="Pawchive Downloader icon" width="120">
</p>

一个使用 **PySide6** 编写的 Android 图集下载工具。它可以扫描 Pawchive 画师主页中的图集，预览封面和标题，再将选中的图片或帖子附件保存到手机指定文件夹。

> 本项目是非官方工具，与 Pawchive、Pixiv、Fanbox 及其他相关服务没有隶属或认可关系。请只下载你有权保存的内容，并遵守网站规则、版权要求及当地法律。

## 设备要求与兼容性

当前 APK 仅包含 **ARM64（aarch64，64 位 ARM）** 架构。**最低兼容 Android 版本尚未确定**，请先参考以下收到的测试反馈：

| Android 版本 | 当前测试反馈 |
| --- | --- |
| Android 12 | 测试设备启动闪退，原因尚待定位 |
| Android 13、14、15 | 尚未验证，暂不能确认是否能正常启动 |
| Android 16 | 已收到可以正常打开应用的反馈 |

其他 Android 版本暂无测试结论。上述结果仅代表测试设备上的启动情况，不代表同版本所有机型或全部下载功能均已验证；Android 16 也不等于已经确定的最低系统要求。

反馈兼容性问题时，请注明 APK 构建来源或日期、手机型号、Android 版本及启动表现。如有崩溃日志，请先移除私人信息，再通过 Issue 提供。后续会根据补充测试和闪退原因更新此表。

## 功能

- 扫描支持的 Pawchive 画师主页，读取图集标题、日期、封面和可下载文件类型。
- 扫描完成后打开图集选择窗口；默认全部选中，也可以逐个取消。
- 支持从新到旧或从旧到新排序，并可暂停、继续或结束扫描。
- 下载图片及页面提供的直链附件，例如 ZIP、MP4、PSD 等格式。
- 默认按图集标题创建文件夹；也可以平铺保存，并按日期给文件编号。
- 显示当前文件下载进度、图集序号和运行日志。
- 使用 Android 系统文件夹选择器选择保存位置。

## 获取 APK

本项目通过 GitHub Actions 在云端构建，不需要在电脑上安装 WSL2、Android Studio 或本地 Android SDK。

1. 登录 GitHub，打开仓库的 **Actions** 页面，选择 **Build Pawchive Android APK**。
2. 打开最近一次成功的运行记录，在页面底部的 **Artifacts** 下载 `PawchiveDownloader-release-APK`。
3. 解压下载文件，将 APK 传到 Android 手机并安装。若手机询问是否允许从当前文件管理器安装应用，请按系统提示授权。

构建产物保留 14 天；如果没有可下载的产物，可等待维护者重新构建，或按下方说明 Fork 后自行构建。具有仓库写入权限的维护者可点击 **Run workflow** 运行构建；工作流也会在 `main` 分支的应用或构建文件变更后自动运行。

## 签名密钥配置

正式 APK 使用仓库维护者的 Android 发布密钥签名。工作流从 GitHub Actions Secrets 读取密钥，不应将密钥文件或密码提交到仓库。

在仓库 **Settings → Secrets and variables → Actions** 中配置：

| Secret 名称 | 内容 |
| --- | --- |
| `ANDROID_KEYSTORE_BASE64` | 发布用 `.p12` 密钥库文件的 Base64 文本 |
| `ANDROID_KEYSTORE_PASSWORD` | 密钥库密码；当前工作流也用作密钥密码 |

密钥库中的密钥别名必须为 `pawchive-release`，与当前工作流的 `P4A_RELEASE_KEYALIAS` 一致；密钥密码与密钥库密码需保持一致。

别把密钥库、密码、Base64 文本或恢复副本放进公开仓库、Issue 或日志。丢失发布密钥后，使用原应用 ID 发布的更新可能无法覆盖旧版本。Fork 本项目的维护者需要创建并配置自己的签名密钥；GitHub 不会把上游仓库的 Secrets 提供给 fork。

## 构建环境

当前工作流使用 Ubuntu 24.04、Python 3.12、Java 17、PySide6 6.12.0，以及 Qt for Python Android 工具链和 Android SDK/NDK。构建流程和依赖版本以 [构建工作流](../.github/workflows/build-android.yml) 为准。

如需自行构建：

1. Fork 本仓库，并在自己的仓库 GitHub Actions Secrets 中配置签名密钥。
2. 在自己的仓库 Actions 页面点击 **Run workflow**，运行 `Build Pawchive Android APK`。
3. 从该次运行的 Artifacts 下载生成的 APK。

## 使用说明

1. 输入完整的 Pawchive 画师主页链接，例如 `https://pawchive.pw/fanbox/user/76050360`。
2. 选择手机上的保存文件夹。
3. 保持默认的扫描选项，或调整排序、图集文件夹和编号设置，然后开始。
4. 扫描完成后检查封面、标题和文件类型，取消不需要的图集，再确认下载。

应用需要联网读取 Pawchive 页面和下载附件。下载先暂存于应用工作目录，再复制到你授权的目标文件夹；成功后会清理该次下载的暂存文件。若目标文件夹写入失败，应用会在日志中提示，暂存内容可能仍留在应用目录中。

## 隐私与安全

- 本项目不要求用户提供 Pawchive 账号密码、访问令牌或 API 密钥。
- 画师主页、封面和附件由应用直接通过网络读取；下载文件写入用户选择的位置。
- 请不要将签名密钥或密码放入代码、提交记录、截图或公开日志。
- 公开仓库意味着源代码、工作流和提交历史都可被任何人查看。发布前请确认历史提交中也没有密钥或其他不应公开的信息。

## 许可

项目代码以 [MIT License](../LICENSE) 发布。PySide6、Qt、Android 工具链及其他依赖分别适用其各自许可证；MIT 许可不替代这些第三方许可。

## English

Pawchive Downloader for Android is an unofficial PySide6 app that scans a Pawchive creator page, lets you choose posts, and saves images and direct-link attachments to a folder selected through Android's system picker. APKs are built by GitHub Actions and signed with the repository maintainer's private release key. See the sections above for build and signing setup. Use the app only for content you are authorized to download, and follow the service's rules and applicable copyright laws.

This project is not affiliated with or endorsed by Pawchive, Pixiv, Fanbox, or other related services. The project code is licensed under the MIT License; third-party components retain their own licenses.

The APK targets ARM64 devices. The minimum compatible Android version has not been established: a test device running Android 12 crashed at launch, Android 16 was reported to launch successfully, and Android 13–15 remain unverified. These reports do not establish compatibility with every device or confirm all download features.
