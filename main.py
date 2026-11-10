"""课件通启动入口。

电脑端运行：  python main.py
安卓端打包：   buildozer android debug（入口自动使用本文件）
"""
from app.app import CourseKitApp

if __name__ == "__main__":
    CourseKitApp().run()
