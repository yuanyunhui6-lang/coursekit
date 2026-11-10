# 课件通 Android 打包与安装指南

本文说明如何用 GitHub Actions 在云端把「课件通」打包成安卓 APK，以及常见问题排查。
**你不需要在本地安装 Android SDK / NDK**，手机、Windows 电脑都用不着装工具链。

---

## 一、整体流程

```
你的电脑（改代码）  →  push 到 GitHub  →  GitHub Actions（云端 Linux + Docker 构建）
                                              ↓
                                      下载 artifact（APK）→ 传到手机安装
```

所需的构建配置都已在本仓库中：

| 文件 | 作用 |
| --- | --- |
| `buildozer.spec` | buildozer 打包配置：应用名、包名、依赖、Android 权限、ML Kit 依赖等 |
| `.github/workflows/build-apk.yml` | GitHub Actions 工作流：用官方 `kivy/buildozer` 镜像执行 `buildozer android debug` |
| `native/android_ocr.py` | 安卓端离线中文 OCR（ML Kit `text-recognition-chinese`） |
| `native/android_pdf.py` | 用系统 `PdfRenderer` 把 PDF 逐页渲染成 PNG |
| `native/android_export.py` | 导出文件到手机「下载/课件通」目录（MediaStore） |
| `native/android_permissions.py` | 运行时权限申请 |
| `native/android_picker.py` | 系统文件选择器（SAF）与系统相机拍照 |

---

## 二、把代码推到 GitHub

在项目根目录（`buildozer.spec` 所在目录）执行：

```powershell
git init
git add .
git commit -m "课件通：首次提交"
git branch -M main
git remote add origin https://github.com/<你的用户名>/<仓库名>.git
git push -u origin main
```

注意事项：

* **不要**把 `.venv/`、`.buildozer/`、`bin/` 提交进去（仓库里的 `.gitignore` 应已忽略；虚拟环境体积大且与本项目无关）。
* 仓库建议设为 **Public**（公开仓库的 Actions 额度免费；私有仓库也会消耗额度）。
* 如果推送时报错，检查是否已在 GitHub 建好空仓库、以及是否配置了 PAT / SSH key。

---

## 三、在 GitHub Actions 上构建 APK

1. 打开仓库页面 → 顶部 **Actions**。
2. 左侧选择 **构建 Android APK**。
3. 右侧点击 **Run workflow** → 选择分支（一般是 `main`）→ **Run workflow**。
4. 等待任务完成（绿色 ✓）。首次构建通常 **40~90 分钟**（要下载 Android SDK/NDK、编译 Python 与 Kivy），
   之后命中缓存一般 **15~30 分钟**。
5. 点进这次运行，页面底部 **Artifacts** 区域下载 `coursekit-debug-apk`（一个 zip，解压得到 `.apk`）。

> 也可以直接 push 代码触发：当改动涉及 `native/`、`app/`、`core/`、`main.py`、`buildozer.spec`
> 或工作流文件时，会自动构建一次。

---

## 四、在手机上安装 APK

1. 把下载到的 `.apk` 传到手机（微信文件传输 / USB 数据线 / 网盘均可）。
2. 用手机文件管理器点开 APK。
3. 系统提示「禁止安装未知来源应用」时，按提示**允许**当前文件管理器/浏览器安装未知应用。
   （设置路径大致为：设置 → 应用 → 特殊权限 → 安装未知应用 → 选择对应的管理器并允许。）
4. 安装完成后桌面出现「课件通」图标。首次使用会请求相机、存储等权限，请允许，
   否则拍照/导出功能不可用。

APK 说明：

* 这是 **debug 版**，已签名（debug 签名），可直接安装，但不能上架应用商店。
* 包含 `arm64-v8a` 与 `armeabi-v7a` 两种架构，覆盖绝大多数安卓手机。
* 应用 ID 是 `org.coursekit.coursekit`，最低支持 Android 7.0（API 24），目标 API 33。
* ML Kit 中文 OCR 模型已打进 APK，**安装后完全离线可用**。

---

## 五、为什么不能直接在 Windows 电脑上打包？

`buildozer android debug` 依赖 `python-for-android`，而 p4a 的官方工具链**只能在 Linux`（或 macOS）**上运行：

* 需要 Linux 下的 Android SDK build-tools、NDK、autoconf/automake/libtool 等交叉编译工具链；
* Windows 原生环境缺少这些工具，`p4a` 直接不支持，硬装也会在编译 Python/Kivy 时失败；
* 另外很多教程要求「真机 + Linux」，是因为本地构建还涉及 SDK license、NDK 路径等问题。

因此本项目的标准做法是：

1. **推荐**：GitHub Actions 云端构建（本文第三、四节），电脑无需任何 Android 工具；
2. 本地调试可用 **Docker Desktop + `kivy/buildozer` 镜像**（见第六节），本质仍是 Linux 容器；
3. 也可以在 **WSL2（Ubuntu）** 里装 buildozer 构建，但首次配置比云端麻烦，不推荐。

> 「本地 ARM 设备不能打包」同理：ARM 架构的 Linux（如树莓派）没有官方预编译的 Android SDK/NDK 工具，
> 交叉编译链不全，p4a 的构建脚本默认面向 x86_64 主机，失败率很高。用云端 x86_64 最省心。

---

## 六、（可选）在本地用 Docker 构建

前提：Windows 上安装 Docker Desktop（WSL2 后端），且能访问 Docker Hub / Google Maven。

```powershell
# 在项目根目录（有 buildozer.spec 的目录）执行
docker run --rm `
  -v ${PWD}:/home/user/hostcwd `
  -v ${HOME}/.buildozer:/home/user/.buildozer `
  kivy/buildozer android debug
```

构建成功后 APK 在本机 `bin/` 目录。若提示写权限不足，先执行
`docker run --rm -v ${PWD}:/home/user/hostcwd kivy/buildozer sudo chown -R 1000:1000 /home/user/hostcwd`
（或让 Docker Desktop 对该目录开启共享/写权限）。

---

## 七、常见失败排查

### 1. 卡在下载 Android SDK / NDK，最后超时（首次构建最常见）

* 现象：日志长时间停在 `Downloading ... android-ndk-r25b-linux.zip` 或 `sdkmanager`。
* 原因：SDK/NDK 体积大（合计 5GB 左右），Google 下载服务器从国内访问不稳定。
* 处理：
  * 重跑一次 workflow（缓存会逐步建立，第二次通常快很多）；
  * 本项目已缓存 `~/.buildozer`，命中缓存后不再重复下载；
  * 实在不行可改用 `ArtemSBulgakov/buildozer-action@v1`（它内置了缓存与权限处理），
    或把 NDK 包预先放进自建缓存。

### 2. SDK license 未接受：`You have not accepted the license agreements`

* 本项目 `buildozer.spec` 已设置 `android.accept_sdk_license = True`；
* CI 里还额外传了环境变量 `APP_ANDROID_ACCEPT_SDK_LICENSE=1`；
* 如果仍报错，检查是不是本地/镜像里 `~/.buildozer` 缓存里的 SDK 与 license 目录被破坏，
  清掉 `~/.buildozer/android/platform` 后重跑。

### 3. Java 版本问题：`Unsupported class file major version` / `JAVA_HOME`

* `android.api = 33` + 当前 p4a 工具链要求 **JDK 17**；
* 官方 `kivy/buildozer` 镜像内已装好合适 JDK，CI 不用管；
* 本地 Docker 构建不要用很旧的镜像 tag；WSL 本地构建请确认 `java -version` 是 17。

### 4. ML Kit 依赖解析失败：`Could not find com.google.mlkit:text-recognition-chinese:16.0.0`

* 原因：Gradle 找不到 Google Maven 仓库（离线/代理/仓库配置丢失）。
* 处理：
  * 检查网络能否访问 `https://maven.google.com`；
  * `python-for-android` 的 Gradle 模板默认已带 `google()` 与 `mavenCentral()`，
    一般无需额外配置；
  * 若确实需要，取消 `buildozer.spec` 里 `android.gradle_repositories` 那行注释：
    ```
    android.gradle_repositories = "maven { url 'https://maven.google.com' }"
    ```
    （这是 buildozer 添加 Gradle 仓库的正确键名；仓库地址含空格时必须加双引号。）
  * 另外确认 `android.enable_androidx = True`（ML Kit 依赖 AndroidX）。

### 5. 构建成功但 `bin/` 里没有 APK

* 看日志最后是否出现 `BUILD SUCCESSFUL`；
* 常见于磁盘空间不足（GitHub 运行器默认剩余空间有限）：本项目工作流已删除一部分预装工具腾出空间，
  若仍失败可再删除 `/opt/hostedtoolcache`；
* 也可能是缓存损坏，删除 Actions 缓存（仓库 Settings → Actions → Caches）后重跑。

### 6. APK 安装失败：`解析软件包时出现问题` / `应用未安装`

* 手机 Android 版本低于 7.0（API 24）不支持，本项目最低 API 24；
* 极少数机型架构是 x86（平板/模拟器）时无法安装 arm 版 APK；
* 之前装过相同包名但签名不同的版本：先卸载旧版再装。

### 7. 运行时报「权限被拒绝」或闪退

* 到 设置 → 应用 → 课件通 → 权限，手动打开相机/存储权限；
* 若导出到「下载」失败：Android 10+ 通过 MediaStore 免权限写入；
  Android 9 及以下需要存储权限并重启 App 后重试；
* 抓日志：手机开 USB 调试后执行 `adb logcat | findstr python`（Windows PowerShell 用 `Select-String`）。

---

## 八、构建产物与配置速查

| 项目 | 值 |
| --- | --- |
| 应用名 | 课件通 |
| 应用 ID | `org.coursekit.coursekit` |
| 版本 | 0.1.0 |
| 最低 / 目标 API | 24 / 33 |
| 架构 | `arm64-v8a`, `armeabi-v7a` |
| Python 依赖 | `python3`, `kivy==2.3.0`, `plyer`, `pyjnius` |
| 安卓原生依赖 | `com.google.mlkit:text-recognition-chinese:16.0.0`（Google Maven） |
| 权限 | CAMERA, READ_EXTERNAL_STORAGE, WRITE_EXTERNAL_STORAGE, READ_MEDIA_IMAGES, INTERNET |

> 注意：安卓端 OCR 只用 ML Kit，**故 requirements 里不含 rapidocr / onnxruntime / opencv / numpy / pymupdf**。
> 这些库是电脑端（RapidOCR）使用的，加进安卓依赖会导致构建失败或 APK 体积暴涨。

---

## 九、已知限制（首次真机测试时请重点验证）

本项目所有安卓原生模块都**无法在本机真机验证**，以下行为需要装机后实测：

1. **ML Kit 中文识别**：`native/android_ocr.py` 通过 pyjnius 调用 ML Kit，识别回调依赖主线程 Looper；
   若调用方（core/）在主线程直接调用 `recognize_lines()`，界面会卡住甚至死锁——
   必须放到后台线程（`threading.Thread`）里调用。
2. **PDF 渲染**：`native/android_pdf.py` 用系统 `PdfRenderer`，加密 PDF 会抛异常并返回空列表。
3. **文件选择器/相机**：`native/android_picker.py` 依赖 `android.activity` 的 `on_activity_result`；
   若选择过程中 App 被系统回收（低内存、旋转屏幕导致 Activity 重建），回调可能丢失，
   本模块 10 分钟后会超时回调 `None`，UI 应允许用户重试。
4. **导出到下载**：Android 10+ 免权限；Android 9 及以下需要存储权限。
