[app]

# ============================================================================
# 课件通 —— Kivy 安卓 App 的 buildozer 配置
# 构建命令（Linux / macOS / Docker，Windows 请用 WSL 或 GitHub Actions）：
#   buildozer android debug
# APK 产物在 bin/ 目录。
# ============================================================================

# 应用显示名称（手机桌面图标下方 / 应用信息页）
title = 课件通

# 包名：最终应用 ID 为 org.coursekit.coursekit
package.name = coursekit
package.domain = org.coursekit

# 源码根目录（相对 buildozer.spec 所在目录）
source.dir = .

# 只把下列扩展名的文件打进 APK（避免把临时文件、日志打进去）
source.include_exts = py,png,jpg,jpeg,kv,atlas,json,txt,md,csv

# 不打包进 APK 的目录：
# - tests：测试代码，桌面运行
# - venv / .venv / .tmp_pip / .pip-cache：本地 Python 环境（体积巨大，绝不能进 APK）
# - docs / .github：文档与 CI 配置
# 说明：以 “.” 开头的目录（.venv/.git/.github）buildozer 默认也会排除，这里显式写出更直观。
source.exclude_dirs = tests, tools, samples, smoke_data, diag_data, data, bin, venv, .venv, .buildozer, .tmp_pip, .pip-cache, docs, .github, .git, .idea, .kivy, __pycache__

# 排除文件模式
source.exclude_patterns = *.pyc, *.pyo, *.log, *.tmp, *.spec

# 版本号（用于 APK 文件名与升级判断）
version = 0.1.0

# 应用图标与启动图（512x512 / 720x1280，见 assets/）
icon.filename = %(source.dir)s/assets/icon.png
presplash.filename = %(source.dir)s/assets/presplash.png

# Python 依赖：
# - python3：p4a 的 Python 解释器
# - kivy==2.3.0：UI 框架，锁定版本保证可复现构建
# - pyjnius：调用 Android Java API（ML Kit / PdfRenderer / MediaStore 都靠它）
# - plyer：跨平台设备能力（桌面端用）
#
# 重要：安卓端离线 OCR 使用 ML Kit（见 android.gradle_dependencies），
# PDF 渲染使用系统 PdfRenderer。
# 绝对不要把 rapidocr / onnxruntime / opencv / numpy / pymupdf 加进 requirements，
# 它们要么没有 p4a 配方、要么会让 APK 体积暴涨甚至构建失败。
requirements = python3,kivy==2.3.0,plyer,pyjnius

# 只允许竖屏（课件阅读以竖屏为主）
orientation = portrait

# 0 = 显示状态栏（用户能看到时间/电量，截图分享课件时更自然）
fullscreen = 0

# ---------------- Android 构建参数 ----------------
# 编译 SDK / 最低支持 / 目标 SDK 统一使用 33（Android 13），满足 Play 商店要求
android.api = 33
android.minapi = 24
android.targetapi = 33

# NDK 版本（p4a 推荐与 API 33 搭配的版本）
android.ndk = 25b

# CPU 架构：只保留主流 ARM 架构，减小 APK 体积
android.archs = arm64-v8a

# 运行时权限（Android 6+ 需要动态申请，见 native/android_permissions.py）：
# CAMERA                  拍照（系统相机）
# READ_EXTERNAL_STORAGE   读取存储（API < 33 的相册/文件访问）
# WRITE_EXTERNAL_STORAGE  写入公共下载目录（仅 API <= 28 的旧系统需要）
# READ_MEDIA_IMAGES       Android 13+ 的图片读取权限
# INTERNET                预留（例如将来上传/同步）
# 说明：如需在 Android 13+ 弹「作业截止提醒」通知，请把 POST_NOTIFICATIONS
# 追加到这一行末尾（native/android_permissions.py 已按系统版本申请该权限，
# 但只有在这里声明过系统才会真正弹窗）。
android.permissions = CAMERA,READ_EXTERNAL_STORAGE,WRITE_EXTERNAL_STORAGE,READ_MEDIA_IMAGES,INTERNET

# ML Kit 中文文字识别（随包模型版：中文模型打进 APK，安装后离线可用）。
# 这是 Google Maven 上的正式产物，会被 p4a 写进 Gradle 依赖。
android.gradle_dependencies = com.google.mlkit:text-recognition-chinese:16.0.0

# ML Kit 依赖 AndroidX，必须开启（p4a 会把 Gradle 工程迁移到 AndroidX）
android.enable_androidx = True

# 自动接受 Android SDK / NDK license（无交互构建，CI 必需）
android.accept_sdk_license = True

# ---- Gradle 仓库（maven 仓库）说明 ----
# 已查证：buildozer.spec 中添加 Gradle 仓库的正确键名是 android.gradle_repositories
# （对应 buildozer 默认模板中的 “(list) Gradle repositories to add”；
#  每个仓库用双引号包裹，多个仓库用逗号分隔，例如：
#      android.gradle_repositories = "maven { url 'https://maven.google.com' }", "maven { url 'https://repo1.maven.org/maven2' }"
#  如果仓库地址包含空格，必须加双引号，否则会被 buildozer 当成多个列表项。）
#
# python-for-android 的 Gradle 工程模板默认已在 buildscript / allprojects
# 中声明 google() 与 mavenCentral()，所以 ML Kit 依赖通常可直接解析，
# 这里无需取消注释。若 CI 出现
#   Could not find com.google.mlkit:text-recognition-chinese:16.0.0
# 的错误，再取消下面一行注释重试：
#android.gradle_repositories = "maven { url 'https://maven.google.com' }"

# 使用 SDL2 启动器（Kivy 默认）
#p4a.bootstrap = sdl2

# 日志级别：2 = 输出 buildozer 的常规构建信息（排查 CI 失败时够用）
android.logcat_filters = *:S python:D


[buildozer]

# 日志级别（0=静默，1=警告，2=信息）
log_level = 2

# 以 root 运行时只警告不中止（Docker / CI 里常见）
warn_on_root = 1
