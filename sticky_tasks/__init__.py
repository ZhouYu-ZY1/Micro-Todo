"""微清单 —— 桌面任务便签应用。"""

from .i18n import t

# 品牌名(中文始终为「微清单」);界面显示请用 app_name() 以跟随语言。
APP_NAME = "微清单"
APP_VERSION = "1.2.1"


def app_name() -> str:
    """当前语言下的应用名称:中文「微清单」,英文「Micro Todo」。"""
    return t("app.name")
