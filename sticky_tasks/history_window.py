"""可嵌入设置窗口的归档数据面板。"""

from datetime import datetime

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QCursor, QFont
from PySide6.QtWidgets import (
    QAbstractItemView, QHBoxLayout, QLabel, QMessageBox, QPushButton,
    QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget,
)

from . import dialogs
from .app_settings import Theme
from .i18n import t
from .task_item import TEXT_MASK


def _rgba(color):
    return f"rgba({color.red()},{color.green()},{color.blue()},{color.alpha()})"


class ArchivePanel(QWidget):
    """按原分组展示归档事项，支持跨分组批量操作。"""

    changed = Signal()

    def __init__(self, store, parent=None):
        super().__init__(parent)
        self.store = store
        self._text_hidden = False
        self._build_ui()
        self.refresh()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        toolbar = QWidget()
        toolbar.setObjectName("archiveToolbar")
        toolbar_layout = QHBoxLayout(toolbar)
        toolbar_layout.setContentsMargins(12, 8, 12, 8)
        self.select_all_btn = QPushButton(t("archive.select_all"))
        self.select_all_btn.setObjectName("ghostButton")
        self.select_all_btn.setCursor(QCursor(Qt.PointingHandCursor))
        self.select_all_btn.clicked.connect(self._toggle_all)
        toolbar_layout.addWidget(self.select_all_btn)
        toolbar_layout.addStretch()
        self.count_label = QLabel()
        self.count_label.setObjectName("mutedLabel")
        toolbar_layout.addWidget(self.count_label)
        root.addWidget(toolbar)

        self.tree = QTreeWidget()
        self.tree.setObjectName("archiveTree")
        self.tree.setColumnCount(3)
        self.tree.setHeaderLabels([
            t("archive.col_task"), t("archive.col_state"), t("archive.col_time"),
        ])
        self.tree.setRootIsDecorated(False)
        self.tree.setAlternatingRowColors(False)
        self.tree.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.tree.setSelectionBehavior(QAbstractItemView.SelectItems)
        self.tree.header().setStretchLastSection(False)
        self.tree.header().resizeSection(0, 250)
        self.tree.header().resizeSection(1, 105)
        self.tree.header().resizeSection(2, 125)
        self.tree.itemChanged.connect(self._update_actions)
        root.addWidget(self.tree, 1)

        actions = QWidget()
        actions.setObjectName("archiveActions")
        actions_layout = QHBoxLayout(actions)
        actions_layout.setContentsMargins(12, 9, 12, 9)
        self.selected_label = QLabel(t("archive.selected_none"))
        self.selected_label.setObjectName("mutedLabel")
        actions_layout.addWidget(self.selected_label)
        actions_layout.addStretch()
        self.delete_btn = QPushButton(t("archive.delete"))
        self.delete_btn.setObjectName("dangerButton")
        self.delete_btn.setCursor(QCursor(Qt.PointingHandCursor))
        self.delete_btn.clicked.connect(self.delete_selected)
        actions_layout.addWidget(self.delete_btn)
        self.restore_btn = QPushButton(t("archive.restore"))
        self.restore_btn.setObjectName("primaryButton")
        self.restore_btn.setCursor(QCursor(Qt.PointingHandCursor))
        self.restore_btn.clicked.connect(self.restore_selected)
        actions_layout.addWidget(self.restore_btn)
        root.addWidget(actions)

    def set_theme(self, theme: Theme):
        bg = theme.bg_color
        text = theme.text_color.name()
        muted = theme.icon_color.name()
        line = _rgba(theme.sep_color)
        hover = _rgba(theme.highlight_color)
        surface = "rgba(255,255,255,7)" if theme.is_dark else "rgba(255,255,255,120)"
        selected = theme.accent_color.name()
        self.setStyleSheet(f"""
ArchivePanel {{ background: transparent; }}
QWidget#archiveToolbar, QWidget#archiveActions {{ background: {surface}; }}
QWidget#archiveToolbar {{ border: 1px solid {line}; border-bottom: none; border-top-left-radius: 11px; border-top-right-radius: 11px; }}
QWidget#archiveActions {{ border: 1px solid {line}; border-top: none; border-bottom-left-radius: 11px; border-bottom-right-radius: 11px; }}
QLabel {{ color: {text}; }} QLabel#mutedLabel {{ color: {muted}; font-size: 11px; }}
QTreeWidget#archiveTree {{ background: {surface}; color: {text}; border: 1px solid {line}; outline: none; }}
QTreeWidget#archiveTree::item {{ min-height: 31px; padding: 2px 6px; }}
QTreeWidget#archiveTree::item:hover {{ background: {hover}; }}
QTreeWidget#archiveTree::item:selected {{ background: {selected}; color: white; }}
QHeaderView::section {{ background: {bg.name()}; color: {muted}; border: none; border-bottom: 1px solid {line}; padding: 7px; font-size: 11px; font-weight: 600; }}
QPushButton {{ min-height: 28px; padding: 0 12px; border-radius: 7px; color: {text}; background: {hover}; border: 1px solid {line}; }}
QPushButton:hover {{ border-color: {theme.icon_color.name()}; }}
QPushButton#primaryButton {{ color: white; background: {selected}; border-color: {selected}; }}
QPushButton#dangerButton {{ color: #e56b6f; }}
QPushButton:disabled {{ color: {muted}; background: transparent; }}
""")

    def refresh(self):
        self.tree.blockSignals(True)
        self.tree.clear()
        total = 0
        for entry in self.store.deleted_tasks_by_group():
            group, tasks = entry["group"], entry["tasks"]
            label = group.name + (t("archive.group_pending") if group.deleted else "")
            parent = QTreeWidgetItem([f"{label}  ({len(tasks)})", "", ""])
            parent.setFlags(parent.flags() & ~Qt.ItemIsUserCheckable)
            font = QFont(parent.font(0)); font.setBold(True); parent.setFont(0, font)
            self.tree.addTopLevelItem(parent)
            parent.setExpanded(True)
            for task in tasks:
                text = TEXT_MASK if self._text_hidden and task.text else (task.text or t("task.empty_text"))
                stamp = task.deleted_at or task.completed_at or task.created_at
                item = QTreeWidgetItem([text, t("archive.state_completed") if task.completed else t("archive.state_archived"), self._format_time(stamp)])
                item.setData(0, Qt.UserRole, task.id)
                item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
                item.setCheckState(0, Qt.Unchecked)
                parent.addChild(item)
                total += 1
        self.tree.blockSignals(False)
        self.count_label.setText(t("archive.count", n=total))
        self._update_actions()

    def set_text_hidden(self, hidden):
        if self._text_hidden != hidden:
            self._text_hidden = hidden
            self.refresh()

    def _task_items(self):
        for index in range(self.tree.topLevelItemCount()):
            group = self.tree.topLevelItem(index)
            for child_index in range(group.childCount()):
                yield group.child(child_index)

    def _checked_ids(self):
        return [item.data(0, Qt.UserRole) for item in self._task_items() if item.checkState(0) == Qt.Checked]

    def _toggle_all(self):
        items = list(self._task_items())
        check = Qt.Unchecked if items and all(item.checkState(0) == Qt.Checked for item in items) else Qt.Checked
        self.tree.blockSignals(True)
        for item in items:
            item.setCheckState(0, check)
        self.tree.blockSignals(False)
        self._update_actions()

    def _update_actions(self):
        count = len(self._checked_ids())
        total = sum(1 for _ in self._task_items())
        self.restore_btn.setEnabled(count > 0)
        self.delete_btn.setEnabled(count > 0)
        self.restore_btn.setText(t("archive.restore_n", n=count) if count else t("archive.restore"))
        self.delete_btn.setText(t("archive.delete_n", n=count) if count else t("archive.delete"))
        self.selected_label.setText(t("archive.selected", n=count) if count else t("archive.selected_none"))
        self.select_all_btn.setText(t("archive.clear_all") if total and count == total else t("archive.select_all"))

    def restore_selected(self):
        ids = self._checked_ids()
        if ids:
            self.store.restore_many(ids)
            self.refresh()
            self.changed.emit()

    def delete_selected(self, confirm=True):
        ids = self._checked_ids()
        if not ids:
            return
        if confirm and dialogs.question(self, t("archive.delete_confirm_title"), t("archive.delete_confirm", n=len(ids))) != QMessageBox.Yes:
            return
        self.store.permanent_delete(ids)
        self.refresh()
        self.changed.emit()

    @staticmethod
    def _format_time(value):
        try:
            return datetime.fromisoformat(value).strftime("%Y-%m-%d %H:%M")
        except (TypeError, ValueError):
            return ""
