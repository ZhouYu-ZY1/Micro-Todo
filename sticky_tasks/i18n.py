"""多语言支持:中文 / English。

极简方案:查表翻译,不走 Qt Linguist。界面文案在启动时按
当前语言构建,改语言后提示重启生效。
"""

LANG_ZH = "zh"
LANG_EN = "en"
SUPPORTED = (LANG_ZH, LANG_EN)

_current = LANG_ZH


def set_language(lang: str):
    """设置当前语言;不支持的值回退到中文。"""
    global _current
    _current = lang if lang in SUPPORTED else LANG_ZH


def get_language() -> str:
    return _current


def t(key: str, **fmt) -> str:
    """按 key 取当前语言文案,可用关键字参数填充占位符。

    缺 key 时直接返回 key 本身,保证永不崩。
    """
    table = _TRANSLATIONS.get(_current) or _TRANSLATIONS[LANG_ZH]
    text = table.get(key)
    if text is None:
        text = (_TRANSLATIONS[LANG_ZH].get(key) or key)
    if fmt:
        try:
            text = text.format(**fmt)
        except (KeyError, IndexError):
            pass
    return text


# 注:"已完成  {n}" 的双空格是排版设计,两种语言均保留。
_TRANSLATIONS = {
    LANG_ZH: {
        # ---- 通用 ----
        "app.name": "微清单",
        "common.confirm": "确认",
        "common.cancel": "取消",
        "common.restart_now": "立即重启",
        "common.later": "稍后",
        # ---- 主窗口 ----
        "app.running": "{name} 已在运行,请勿重复打开。",
        "app.crash": "程序遇到了意外错误。\n错误详情已记录到 .sticky_tasks/crash.log，反馈问题时请附带该文件。",
        "app.data_warning": "本地数据提示",
        "main.new_tooltip": "新建任务 (Ctrl+N)",
        "main.empty_hint": "暂无任务 —— 点击分组右侧 + 或按 Ctrl+N 新建",
        "main.new_group": "新建分组",
        "main.completed_count": "已完成  {n}",
        "main.deferred_count": "已搁置  {n}",
        "group.add_task_tooltip": "在此分组新建事项",
        "group.rename": "重命名",
        "group.delete": "归档分组",
        "group.delete_confirm": "确定将分组“{name}”及其中 {count} 个事项归档吗？",
        "group.new_title": "新建分组",
        "group.rename_title": "重命名分组",
        "group.name_label": "分组名称",
        "group.default_name": "Default",
        "task.empty_text": "(空任务)",
        "task.restore_tooltip": "恢复到任务列表",
        "main.settings_tooltip": "设置",
        "main.lock_tooltip": "{action} (Ctrl+L)",
        "main.lock_action_on": "锁定窗口",
        "main.lock_action_off": "解锁窗口",
        "main.menu_quit": "退出",
        "main.menu_minimize": "最小化",
        "main.menu_autodock": "自动贴边",
        "main.menu_open": "打开主窗口",
        "main.dock_pending_label": "待办",
        "main.dock_pending_unit": "项",
        "main.pin_tooltip_on": "取消置顶",
        "main.pin_tooltip_off": "置于最上层",
        "main.eye_tooltip_on": "显示任务内容",
        "main.eye_tooltip_off": "隐藏任务内容",
        # ---- 任务项 ----
        "task.mark_done": "标记为完成",
        "task.edit": "编辑",
        "task.defer": "搁置",
        "task.delete": "归档",
        "task.edit_placeholder": "输入任务…",
        # ---- 设置窗口 ----
        "settings.title": "设置",
        "settings.nav_appearance": "外观",
        "settings.nav_general": "常规",
        "settings.nav_archive": "归档数据",
        "settings.appearance_title": "外观",
        "settings.appearance_lead": "调整便签的颜色、字体与透明度，修改会立即预览。",
        "settings.general_title": "常规",
        "settings.general_lead": "管理应用的基础行为与界面语言。",
        "settings.archive_title": "归档数据",
        "settings.archive_lead": "按原分组查看、恢复或永久删除已归档事项。",
        "settings.archive_unavailable": "当前无法读取归档数据。",
        "settings.section_label": "设置",
        "settings.current_theme": "当前主题 · {name}",
        "settings.current_theme_caption": "当前主题",
        "settings.theme_custom": "自定义",
        "settings.theme_presets": "主题预设",
        # 主题预设名称
        "preset.deep_space": "深空",
        "preset.warm_night": "暖夜",
        "preset.forest": "森林",
        "preset.ocean": "海洋",
        "preset.lavender": "薰衣草",
        "preset.ink_black": "墨黑",
        "preset.paper": "素白",
        "settings.colors_section": "颜色",
        "settings.bg_color_note": "设置主窗口和设置窗口的基础色",
        "settings.text_color_note": "用于任务文字和主要信息",
        "settings.typography_section": "文字与透明度",
        "settings.bg_opacity_note": "窗口越透明，越能融入桌面",
        "settings.language_section": "语言",
        "settings.language_note": "更改后将在重启应用时生效",
        "settings.version": "版本 {version}",
        "settings.presets": "预设",
        "settings.bg_color": "背景颜色",
        "settings.text_color": "字体颜色",
        "settings.font": "字体",
        "settings.font_search": "搜索字体",
        "settings.font_size": "字号",
        "settings.bg_opacity": "背景透明度",
        "settings.language": "界面语言",
        "settings.startup_section": "启动",
        "settings.autostart": "开机自动启动",
        "settings.autostart_note": "登录 Windows 后自动运行，并直接收起为贴边条",
        "settings.autostart_failed": "无法修改开机启动项，可能被安全软件拦截。",
        # ---- 归档数据 ----
        "archive.count": "共 {n} 项",
        "archive.group_pending": "（待恢复分组）",
        "archive.col_task": "事项",
        "archive.col_state": "状态",
        "archive.col_time": "时间",
        "archive.state_completed": "归档（原已完成）",
        "archive.state_archived": "已归档",
        "archive.select_all": "全选",
        "archive.clear_all": "清除全选",
        "archive.selected": "已选择 {n} 项",
        "archive.selected_none": "未选择事项",
        "archive.restore": "恢复到原分组",
        "archive.restore_n": "恢复到原分组 ({n})",
        "archive.delete": "永久删除",
        "archive.delete_n": "永久删除 ({n})",
        "archive.delete_confirm_title": "永久删除",
        "archive.delete_confirm": "确定永久删除选中的 {n} 个事项吗？此操作无法恢复。",
        "settings.save_preset_btn": "保存为自定义预设",
        "settings.custom_preset_tip": "自定义预设",
        "settings.no_custom_preset": "尚未保存自定义预设",
        "settings.pick_bg": "选择背景颜色",
        "settings.pick_text": "选择字体颜色",
        "settings.lang_confirm": "界面语言将切换为{lang}，确定吗？",
        "settings.lang_restart": "语言已切换，将在重启后生效。",
    },
    LANG_EN: {
        # ---- Common ----
        "app.name": "Micro Todo",
        "common.confirm": "Confirm",
        "common.cancel": "Cancel",
        "common.restart_now": "Restart now",
        "common.later": "Later",
        # ---- Main window ----
        "app.running": "{name} is already running.",
        "app.crash": "An unexpected error occurred.\nDetails were saved to .sticky_tasks/crash.log — please attach it when reporting.",
        "app.data_warning": "Local Data Notice",
        "main.new_tooltip": "New task (Ctrl+N)",
        "main.empty_hint": "No tasks — click a group + or press Ctrl+N",
        "main.new_group": "New group",
        "main.completed_count": "Completed  {n}",
        "main.deferred_count": "Deferred  {n}",
        "group.add_task_tooltip": "Add a task to this group",
        "group.rename": "Rename",
        "group.delete": "Archive group",
        "group.delete_confirm": "Archive group \"{name}\" and its {count} items?",
        "group.new_title": "New group",
        "group.rename_title": "Rename group",
        "group.name_label": "Group name",
        "group.default_name": "Default",
        "task.empty_text": "(empty task)",
        "task.restore_tooltip": "Restore to task list",
        "main.settings_tooltip": "Settings",
        "main.lock_tooltip": "{action} (Ctrl+L)",
        "main.lock_action_on": "Lock window",
        "main.lock_action_off": "Unlock window",
        "main.menu_quit": "Quit",
        "main.menu_minimize": "Minimize",
        "main.menu_autodock": "Auto-dock to edge",
        "main.menu_open": "Open main window",
        "main.dock_pending_label": "Pending",
        "main.dock_pending_unit": "tasks",
        "main.pin_tooltip_on": "Unpin",
        "main.pin_tooltip_off": "Keep on top",
        "main.eye_tooltip_on": "Show task text",
        "main.eye_tooltip_off": "Hide task text",
        # ---- Task item ----
        "task.mark_done": "Mark as done",
        "task.edit": "Edit",
        "task.defer": "Defer",
        "task.delete": "Archive",
        "task.edit_placeholder": "Type a task…",
        # ---- Settings window ----
        "settings.title": "Settings",
        "settings.nav_appearance": "Appearance",
        "settings.nav_general": "General",
        "settings.nav_archive": "Archive data",
        "settings.appearance_title": "Appearance",
        "settings.appearance_lead": "Adjust note colors, typography, and opacity with a live preview.",
        "settings.general_title": "General",
        "settings.general_lead": "Manage basic app behavior and interface language.",
        "settings.archive_title": "Archive data",
        "settings.archive_lead": "Review, restore, or permanently delete archived items by original group.",
        "settings.archive_unavailable": "Archive data is unavailable.",
        "settings.section_label": "Settings",
        "settings.current_theme": "Current theme · {name}",
        "settings.current_theme_caption": "Current theme",
        "settings.theme_custom": "Custom",
        "settings.theme_presets": "Theme presets",
        # Preset names
        "preset.deep_space": "Deep Space",
        "preset.warm_night": "Warm Night",
        "preset.forest": "Forest",
        "preset.ocean": "Ocean",
        "preset.lavender": "Lavender",
        "preset.ink_black": "Ink Black",
        "preset.paper": "Paper",
        "settings.colors_section": "Colors",
        "settings.bg_color_note": "Sets the base color of the main and settings windows",
        "settings.text_color_note": "Used for task text and primary information",
        "settings.typography_section": "Typography and opacity",
        "settings.bg_opacity_note": "More transparency helps the window blend into the desktop",
        "settings.language_section": "Language",
        "settings.language_note": "Changes take effect after restarting the app",
        "settings.version": "Version {version}",
        "settings.presets": "Presets",
        "settings.bg_color": "Background color",
        "settings.text_color": "Text color",
        "settings.font": "Font",
        "settings.font_search": "Search fonts",
        "settings.font_size": "Font size",
        "settings.bg_opacity": "Background opacity",
        "settings.language": "Interface language",
        "settings.startup_section": "Startup",
        "settings.autostart": "Launch at startup",
        "settings.autostart_note": "Runs after you sign in to Windows, starting as an edge bar",
        "settings.autostart_failed": "Could not change the startup entry. Security software may be blocking it.",
        # ---- Archive data ----
        "archive.count": "{n} items",
        "archive.group_pending": " (group to restore)",
        "archive.col_task": "Item",
        "archive.col_state": "State",
        "archive.col_time": "Time",
        "archive.state_completed": "Archived (was done)",
        "archive.state_archived": "Archived",
        "archive.select_all": "Select all",
        "archive.clear_all": "Clear all",
        "archive.selected": "{n} selected",
        "archive.selected_none": "No items selected",
        "archive.restore": "Restore to group",
        "archive.restore_n": "Restore to group ({n})",
        "archive.delete": "Delete forever",
        "archive.delete_n": "Delete forever ({n})",
        "archive.delete_confirm_title": "Delete forever",
        "archive.delete_confirm": "Permanently delete {n} selected items? This cannot be undone.",
        "settings.save_preset_btn": "Save as preset",
        "settings.custom_preset_tip": "Custom preset",
        "settings.no_custom_preset": "No custom preset saved",
        "settings.pick_bg": "Pick background color",
        "settings.pick_text": "Pick text color",
        "settings.lang_confirm": "Switch interface language to {lang}?",
        "settings.lang_restart": "Language switched. It will take effect after a restart.",
    },
}
