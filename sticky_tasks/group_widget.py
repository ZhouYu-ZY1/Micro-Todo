"""分组任务列表组件。"""

from PySide6.QtCore import QPoint, QSize, QTimer, Qt, Signal, QEvent
from PySide6.QtGui import QCursor, QFont
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QMenu, QPushButton, QVBoxLayout, QWidget,
)

from .app_settings import Theme
from .icons import svg_icon
from .i18n import t
from .task_item import TaskItem, TEXT_MASK, wrap_for_label


class _GroupHeader(QFrame):
    toggled = Signal()
    add_requested = Signal()
    rename_requested = Signal()
    delete_requested = Signal()
    drag_started = Signal(str, QPoint)
    drag_moved = Signal(str, QPoint)
    drag_finished = Signal(str)

    LONG_PRESS_MS = 450

    def __init__(self, group):
        super().__init__()
        self.group = group
        self._locked = False
        self._dragging = False
        self._press_global_pos = None
        self._menu_style = ""
        self.setObjectName("groupHeader")
        self.setMouseTracking(True)
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(self.LONG_PRESS_MS)
        self._timer.timeout.connect(self._activate_drag)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(9, 7, 7, 7)
        layout.setSpacing(6)
        self.chevron = QPushButton()
        self.chevron.setObjectName("groupChevron")
        self.chevron.setFixedSize(24, 24)
        self.chevron.setIconSize(QSize(14, 14))
        self.chevron.setFocusPolicy(Qt.NoFocus)
        self.chevron.clicked.connect(self.toggled)
        layout.addWidget(self.chevron)
        self.name_label = QLabel(group.name)
        self.name_label.setObjectName("groupName")
        self.name_label.installEventFilter(self)
        layout.addWidget(self.name_label, 1)
        self.count_label = QLabel("0")
        self.count_label.setObjectName("groupCount")
        self.count_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.count_label)
        self.add_btn = QPushButton()
        self.add_btn.setObjectName("groupAddBtn")
        self.add_btn.setFixedSize(28, 28)
        self.add_btn.setIconSize(QSize(16, 16))
        self.add_btn.setFocusPolicy(Qt.NoFocus)
        self.add_btn.setCursor(QCursor(Qt.PointingHandCursor))
        self.add_btn.setToolTip(t("group.add_task_tooltip"))
        self.add_btn.clicked.connect(self.add_requested)
        layout.addWidget(self.add_btn)

    def set_count(self, count):
        self.count_label.setText(str(count))

    def set_expanded(self, expanded):
        self.group.is_expanded = expanded
        self._refresh_chevron()

    def _refresh_chevron(self):
        if not hasattr(self, "_icon_color"):
            return
        name = "chevron-down" if self.group.is_expanded else "chevron-right"
        self.chevron.setIcon(svg_icon(name, self._icon_color, 14))

    def set_theme(self, theme: Theme):
        self._icon_color = theme.icon_color
        self._refresh_chevron()
        self.add_btn.setIcon(svg_icon("add", theme.icon_color, 16))
        self.name_label.setFont(QFont(theme.font_family, max(9, theme.font_size - 1)))
        self.count_label.setFont(QFont(theme.font_family, max(9, theme.font_size - 2)))
        bg = theme.bg_color.lighter(115 if theme.is_dark else 101)
        text = theme.text_color
        acc = theme.accent_color
        self._menu_style = (
            f"QMenu {{ background: {bg.name()}; color: {text.name()}; "
            "border: 1px solid rgba(128,128,128,45); border-radius: 9px; "
            "padding: 5px; } QMenu::item { padding: 7px 24px; "
            "border-radius: 6px; } QMenu::item:selected { "
            f"background: rgba({acc.red()},{acc.green()},{acc.blue()},55); }}"
        )

    def set_locked(self, locked):
        self._locked = locked
        self.add_btn.setVisible(not locked)
        if not locked:
            self.add_btn.show()
        if locked and self._dragging:
            self._finish_drag()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton and not self._locked:
            self._press_global_pos = event.globalPosition().toPoint()
            self._timer.start()
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._press_global_pos is not None and event.buttons() & Qt.LeftButton:
            pos = event.globalPosition().toPoint()
            if self._dragging:
                self.drag_moved.emit(self.group.id, pos)
            elif (pos - self._press_global_pos).manhattanLength() > 20:
                self._cancel_drag()
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton and (self._press_global_pos is not None or self._dragging):
            self._finish_drag()
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def _activate_drag(self):
        if self._press_global_pos is None or self._locked:
            return
        self._dragging = True
        self.grabMouse()
        self.setCursor(QCursor(Qt.ClosedHandCursor))
        self.drag_started.emit(self.group.id, self._press_global_pos)

    def _cancel_drag(self):
        self._timer.stop()
        self._press_global_pos = None

    def _finish_drag(self):
        was_dragging = self._dragging
        self._dragging = False
        self._cancel_drag()
        try:
            self.releaseMouse()
        except RuntimeError:
            pass
        self.setCursor(QCursor(Qt.ArrowCursor))
        if was_dragging:
            self.drag_finished.emit(self.group.id)

    def eventFilter(self, obj, event):
        if obj is self.name_label:
            if event.type() == QEvent.MouseButtonPress and event.button() == Qt.LeftButton:
                self.mousePressEvent(event)
                return True
            if event.type() == QEvent.MouseMove and event.buttons() & Qt.LeftButton:
                self.mouseMoveEvent(event)
                return True
            if event.type() == QEvent.MouseButtonRelease and event.button() == Qt.LeftButton:
                self.mouseReleaseEvent(event)
                return True
        return super().eventFilter(obj, event)

    def contextMenuEvent(self, event):
        if self._locked:
            return
        menu = QMenu(self)
        if self._menu_style:
            menu.setStyleSheet(self._menu_style)
        rename = menu.addAction(t("group.rename"))
        delete = menu.addAction(t("group.delete"))
        chosen = menu.exec(event.globalPos())
        if chosen is rename:
            self.rename_requested.emit()
        elif chosen is delete:
            self.delete_requested.emit()


class _StatusRow(QFrame):
    restored = Signal(str)
    deleted = Signal(str)

    def __init__(self, task, hidden=False):
        super().__init__()
        self.task = task
        self._hidden = hidden
        self._menu_style = ""
        self.setObjectName("completedItem")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 6, 7, 6)
        layout.setSpacing(8)
        self.label = QLabel()
        self.label.setObjectName("doneTextDone" if task.state == "completed" else "taskText")
        self.label.setWordWrap(True)
        self.label.setTextFormat(Qt.PlainText)
        layout.addWidget(self.label, 1)
        restore = QPushButton()
        restore.setObjectName("restoreBtn")
        restore.setFixedSize(24, 24)
        restore.setIconSize(QSize(14, 14))
        restore.setFocusPolicy(Qt.NoFocus)
        restore.setToolTip(t("task.restore_tooltip"))
        restore.clicked.connect(lambda: self.restored.emit(task.id))
        layout.addWidget(restore)
        self._refresh_text()

    def _refresh_text(self):
        text = TEXT_MASK if self._hidden and self.task.text else (self.task.text or t("task.empty_text"))
        self.label.setText(text if text == TEXT_MASK else wrap_for_label(text))

    def set_theme(self, theme: Theme):
        font = QFont(theme.font_family)
        font.setPixelSize(max(9, theme.font_size - 1))
        self.label.setFont(font)
        self.findChild(QPushButton, "restoreBtn").setIcon(
            svg_icon("restore", theme.icon_color, 14)
        )
        bg = theme.bg_color.lighter(115 if theme.is_dark else 101)
        text = theme.text_color
        acc = theme.accent_color
        self._menu_style = (
            f"QMenu {{ background: {bg.name()}; color: {text.name()}; "
            "border: 1px solid rgba(128,128,128,45); border-radius: 9px; "
            "padding: 5px; } QMenu::item { padding: 7px 24px; "
            "border-radius: 6px; } QMenu::item:selected { "
            f"background: rgba({acc.red()},{acc.green()},{acc.blue()},55); }}"
        )

    def set_text_hidden(self, hidden):
        self._hidden = hidden
        self._refresh_text()

    def contextMenuEvent(self, event):
        menu = QMenu(self)
        if self._menu_style:
            menu.setStyleSheet(self._menu_style)
        delete = menu.addAction(t("task.delete"))
        if menu.exec(event.globalPos()) is delete:
            self.deleted.emit(self.task.id)


class TaskGroupWidget(QWidget):
    """一个活跃分组及其任务状态二级列表。"""

    add_requested = Signal(str)
    rename_requested = Signal(str)
    delete_requested = Signal(str)
    group_drag_started = Signal(str, QPoint)
    group_drag_moved = Signal(str, QPoint)
    group_drag_finished = Signal(str)
    task_completed = Signal(str)
    task_deferred = Signal(str)
    task_changed = Signal(str, str)
    task_deleted = Signal(str)
    task_drag_started = Signal(str, str, QPoint)
    task_drag_moved = Signal(str, str, QPoint)
    task_drag_finished = Signal(str, str)
    task_restored = Signal(str)
    task_completed_deleted = Signal(str)
    completed_toggled = Signal(str, bool)
    deferred_toggled = Signal(str, bool)
    group_toggled = Signal(str, bool)

    def __init__(
        self, group, active_tasks, completed_tasks, deferred_tasks=None, parent=None,
    ):
        super().__init__(parent)
        self.group = group
        self._locked = False
        self._text_hidden = False
        self._active_items = {}
        self._completed_rows = {}
        self._deferred_rows = {}
        self.setObjectName("taskGroup")
        self.header = _GroupHeader(group)
        self.header.toggled.connect(self._toggle_group)
        self.header.add_requested.connect(lambda: self.add_requested.emit(group.id))
        self.header.rename_requested.connect(lambda: self.rename_requested.emit(group.id))
        self.header.delete_requested.connect(lambda: self.delete_requested.emit(group.id))
        self.header.drag_started.connect(self.group_drag_started)
        self.header.drag_moved.connect(self.group_drag_moved)
        self.header.drag_finished.connect(self.group_drag_finished)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(3)
        root.addWidget(self.header)
        self.body = QWidget()
        self.body_layout = QVBoxLayout(self.body)
        self.body_layout.setContentsMargins(0, 2, 0, 2)
        self.body_layout.setSpacing(1)
        root.addWidget(self.body)
        self.active_body = QWidget()
        self.active_layout = QVBoxLayout(self.active_body)
        self.active_layout.setContentsMargins(0, 0, 0, 0)
        self.active_layout.setSpacing(2)
        self.body_layout.addWidget(self.active_body)
        self.completed_title, self.completed_body, self.completed_layout = self._add_status_section()
        self.deferred_title, self.deferred_body, self.deferred_layout = self._add_status_section()
        self.completed_title.clicked.connect(self._toggle_completed)
        self.deferred_title.clicked.connect(self._toggle_deferred)
        self.refresh(active_tasks, completed_tasks, deferred_tasks or [])

    def _add_status_section(self):
        title = QPushButton()
        title.setObjectName("groupCompletedBtn")
        title.setIconSize(QSize(13, 13))
        title.setFocusPolicy(Qt.NoFocus)
        self.body_layout.addWidget(title)
        body = QWidget()
        layout = QVBoxLayout(body)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)
        self.body_layout.addWidget(body)
        return title, body, layout

    def _clear_layout(self, layout):
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

    def refresh(self, active_tasks, completed_tasks, deferred_tasks=None):
        deferred_tasks = deferred_tasks or []
        for layout in (
            self.active_layout, self.completed_layout, self.deferred_layout,
        ):
            self._clear_layout(layout)
        self._active_items.clear()
        self._completed_rows.clear()
        self._deferred_rows.clear()
        for task in active_tasks:
            item = TaskItem(task)
            item.completed.connect(self.task_completed)
            item.deferred.connect(self.task_deferred)
            item.text_changed.connect(self.task_changed)
            item.delete_requested.connect(self.task_deleted)
            item.drag_started.connect(lambda tid, pos, gid=self.group.id: self.task_drag_started.emit(gid, tid, pos))
            item.drag_moved.connect(lambda tid, pos, gid=self.group.id: self.task_drag_moved.emit(gid, tid, pos))
            item.drag_finished.connect(lambda tid, gid=self.group.id: self.task_drag_finished.emit(gid, tid))
            item.set_text_hidden(self._text_hidden)
            self.active_layout.addWidget(item)
            self._active_items[task.id] = item
        self._fill_status_rows(completed_tasks, self.completed_layout, self._completed_rows)
        self._fill_status_rows(deferred_tasks, self.deferred_layout, self._deferred_rows)
        self.header.set_count(len(active_tasks))
        self._refresh_status_sections()
        self.body.setVisible(bool(self.group.is_expanded))

    def _fill_status_rows(self, tasks, layout, rows):
        for task in tasks:
            row = _StatusRow(task, self._text_hidden)
            row.restored.connect(self.task_restored)
            row.deleted.connect(self.task_completed_deleted)
            layout.addWidget(row)
            rows[task.id] = row

    def _refresh_status_sections(self):
        sections = (
            ("completed", self.completed_title, self.completed_body, self._completed_rows),
            ("deferred", self.deferred_title, self.deferred_body, self._deferred_rows),
        )
        for name, title, body, rows in sections:
            expanded = getattr(self.group, f"{name}_expanded")
            title.setText(t(f"main.{name}_count", n=len(rows)))
            if hasattr(self, "_theme"):
                icon_name = "chevron-down" if expanded else "chevron-right"
                title.setIcon(svg_icon(icon_name, self._theme.icon_color, 13))
            body.setVisible(bool(expanded and rows))

    def _toggle_group(self):
        self.group.is_expanded = not self.group.is_expanded
        self.header.set_expanded(self.group.is_expanded)
        self.body.setVisible(self.group.is_expanded)
        self.group_toggled.emit(self.group.id, self.group.is_expanded)

    def _toggle_status(self, name, signal):
        attr = f"{name}_expanded"
        setattr(self.group, attr, not getattr(self.group, attr))
        self._refresh_status_sections()
        signal.emit(self.group.id, getattr(self.group, attr))

    def _toggle_completed(self):
        self._toggle_status("completed", self.completed_toggled)

    def _toggle_deferred(self):
        self._toggle_status("deferred", self.deferred_toggled)

    def set_theme(self, theme):
        self._theme = theme
        self.header.set_theme(theme)
        self._refresh_status_sections()
        for item in self._active_items.values():
            item.set_theme(theme)
        for rows in (self._completed_rows, self._deferred_rows):
            for row in rows.values():
                row.set_theme(theme)

    def set_locked(self, locked):
        self._locked = locked
        self.header.set_locked(locked)
        for item in self._active_items.values():
            item.set_locked(locked)
        for title in (self.completed_title, self.deferred_title):
            title.setEnabled(not locked)

    def set_text_hidden(self, hidden):
        self._text_hidden = hidden
        for item in self._active_items.values():
            item.set_text_hidden(hidden)
        for rows in (self._completed_rows, self._deferred_rows):
            for row in rows.values():
                row.set_text_hidden(hidden)

    def ordered_task_items(self):
        return [
            self.active_layout.itemAt(index).widget()
            for index in range(self.active_layout.count())
            if isinstance(self.active_layout.itemAt(index).widget(), TaskItem)
        ]
