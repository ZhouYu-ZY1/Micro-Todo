"""开机自启动:读写 HKCU 的 Run 注册表项(仅 Windows 有效)。

用注册表而不是启动文件夹:不需要额外复制快捷方式,卸载时可由安装包
在 [Registry] 段用 uninsdeletevalue 一并清理,不留残值。

项名固定用中文显示名,不跟随界面语言:否则切换语言后会在 Run 里
留下两个指向同一程序的重复项,安装包卸载时也无法把它清干净。
"""

import sys
from pathlib import Path

try:
    import winreg
except ImportError:  # 非 Windows 平台
    winreg = None

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
# 值名必须是纯 ASCII。实测中文值名的启动项(如"微清单")会被安全软件
# (本机为火绒)在几秒内静默清理:写入 API 返回成功,开机却不会启动,
# 排查起来毫无头绪。改名要同步 微清单.iss 的 [Registry] 段。
VALUE_NAME = "MicroTodo"
# 开机自启动时附带的参数:程序据此直接以贴边条形态启动,不弹主窗口
AUTOSTART_FLAG = "--autostart"


def _command() -> str:
    """开机要执行的命令行。

    路径一律加引号:安装目录默认在 %LOCALAPPDATA%\\Programs\\Micro Todo,
    用户名含空格时未加引号会导致命令行被切断、开机启动静默失败。
    """
    executable = Path(sys.executable)
    if getattr(sys, "frozen", False):
        return f'"{executable}" {AUTOSTART_FLAG}'
    # 源码态:用当前解释器跑项目根目录下的 main.py
    entry = Path(__file__).resolve().parent.parent / "main.py"
    return f'"{executable}" "{entry}" {AUTOSTART_FLAG}'


def is_supported() -> bool:
    return winreg is not None


def is_enabled() -> bool:
    """当前是否已设置开机自启动。"""
    if winreg is None:
        return False
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
            value, _ = winreg.QueryValueEx(key, VALUE_NAME)
    except OSError:
        return False
    return bool(value)


def set_enabled(enabled: bool) -> bool:
    """写入或删除自启动项,返回是否真正生效。

    失败(注册表被安全软件拦截、无权限等)不抛异常,由调用方决定怎么提示。
    写完回读一次:安全软件可能让写入"成功"却把值丢弃,回读能挡住这种情况。
    """
    if winreg is None:
        return False
    try:
        if enabled:
            with winreg.CreateKeyEx(
                winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE
            ) as key:
                winreg.SetValueEx(key, VALUE_NAME, 0, winreg.REG_SZ, _command())
        else:
            try:
                with winreg.OpenKey(
                    winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE
                ) as key:
                    winreg.DeleteValue(key, VALUE_NAME)
            except FileNotFoundError:
                pass  # 本来就没有这一项
    except OSError:
        return False
    return is_enabled() is enabled


def refresh() -> None:
    """开机自启动已开启时,把记录的命令行更新为当前程序路径。

    程序被安装到新目录(或换版本重装)后,Run 里可能还指向旧路径,
    开机时会静默启动失败;每次启动顺手校正一次。
    """
    if winreg is None or not is_enabled():
        return
    try:
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE
        ) as key:
            current, _ = winreg.QueryValueEx(key, VALUE_NAME)
            wanted = _command()
            if current != wanted:
                winreg.SetValueEx(key, VALUE_NAME, 0, winreg.REG_SZ, wanted)
    except OSError:
        pass
