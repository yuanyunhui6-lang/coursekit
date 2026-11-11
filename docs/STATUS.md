# 项目进度与待办（2026-11-10 晚）

## 一句话状态

App 代码已完成并在电脑端验证通过；已推送到 GitHub；**云端打包 APK 失败在 buildozer 步骤，等拿到日志修配置**。

## 已完成

- [x] Kivy App「课件通」全部功能代码（拍照/相册/PDF 导入、OCR、切题、搜索、标签、收藏、作业截止、导出 Markdown/Word）
- [x] 电脑端验证：`pytest` 23 项通过；真实 RapidOCR 识别示例图切出 6 题；GUI 功能测试 15 项通过；界面截图正常
- [x] Android 原生模块：ML Kit OCR、PdfRenderer、SAF 文件选择、系统相机、MediaStore 导出、权限
- [x] 打包配置：`buildozer.spec`（arm64-v8a / ML Kit 中文离线模型）、`.github/workflows/build-apk.yml`
- [x] 本地 git 提交：`ed8ff36`，已推到 GitHub
- [x] 平板已通过无线 ADB 连接（荣耀平板 GT Pro / Android 17 / arm64-v8a / `NotoSansCJK-Regular.ttc` 字体确认存在）

## 仓库与运行

- 仓库：https://github.com/yuanyunhui6-lang/coursekit
- 失败运行：https://github.com/yuanyunhui6-lang/coursekit/actions/runs/42838409933
  - 失败步骤：第 7 步「构建 debug APK」（docker 内 buildozer）
  - 前面步骤：检出、缓存、腾磁盘、拉取 kivy/buildozer 镜像 全部成功
- 本机运行：`.venv\Scripts\python.exe main.py`
- 本机测试：`.venv\Scripts\python.exe -m pytest tests -q`；`python tools\functional_test.py`；`python tools\ocr_check.py samples\sample_slide.jpg`

## 明天的待办

1. **取 CI 失败日志**（二选一）：
   - 打开运行页面 → 点失败 job → 展开第 7 步 → 截图日志最底部 20~30 行；或
   - 运行页右上角 Download log archive → 解压/放到 `C:\Users\23612\Downloads\` 告诉我路径
2. 根据日志修 `buildozer.spec` / 工作流（最可能：NDK 25b 与新版 p4a 不兼容、API 33 不匹配、ML Kit Gradle 仓库、容器权限）
3. 改完重新 push，触发第二次构建（有缓存，比第一次快）
4. 构建成功后：下载 `coursekit-debug-apk` → 解压出 APK → 放 Downloads 告诉我
5. 我用无线 ADB 安装到平板，截图/点击/logcat 做真机验收，有问题继续改
6. 真机验证点：ML Kit 中文 OCR、拍照、PDF 导入、导出到「下载」、界面字体与布局

## 无线 ADB 注意事项（明天会失效，需重配）

- 平板：设置 → 开发者选项 → 无线调试 → 打开
- 点「使用配对码配对设备」，把 **IP:配对端口 + 6 位配对码** 发我
- 再点无线调试主页面的 **IP:连接端口** 发我
- adb 路径：`C:\Users\23612\Desktop\ai-local-text\应用开发\.platform-tools\platform-tools\adb.exe`
- 注意：明天平板 IP 可能变化；需要时我可以重新 `adb pair` / `adb connect`

## 已知限制（明天后仍需说明）

- 本机与 ARM 平板都无法本地打包 APK，只能 GitHub Actions
- ML Kit / 相机 / SAF 只能真机验证
- 手写体与复杂公式识别有限；公式按纯文本处理
