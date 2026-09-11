"""数据层：SQLite 持久化的任务与分组模型。

不依赖 Qt UI，可单独单元测试。首次使用数据库时会迁移同目录的旧 tasks.json。
"""

from __future__ import annotations

import json
import os
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path


class Task:
    """单个任务。"""

    def __init__(
        self, id, text, group_id, sort_order=0, completed=False, created_at=None,
        completed_at=None, deleted=False, deleted_at=None, state=None,
        state_changed_at=None,
    ):
        self.id = id
        self.text = text
        self.group_id = group_id
        self.sort_order = sort_order
        self.state = state or ("completed" if completed else "active")
        self.completed = self.state == "completed"
        self.created_at = created_at or datetime.now().isoformat()
        self.completed_at = completed_at
        self.state_changed_at = state_changed_at
        self.deleted = deleted
        self.deleted_at = deleted_at

    @classmethod
    def from_row(cls, row):
        keys = row.keys()
        return cls(
            id=row["id"],
            text=row["text"],
            group_id=row["group_id"],
            sort_order=row["sort_order"],
            completed=bool(row["completed"]),
            created_at=row["created_at"],
            completed_at=row["completed_at"],
            deleted=bool(row["deleted"]),
            deleted_at=row["deleted_at"],
            state=row["state"] if "state" in keys else None,
            state_changed_at=row["state_changed_at"] if "state_changed_at" in keys else None,
        )


class TaskGroup:
    """任务分组。"""

    def __init__(
        self, id, name, sort_order=0, is_expanded=True, completed_expanded=False,
        deferred_expanded=False, deleted=False, deleted_at=None,
    ):
        self.id = id
        self.name = name
        self.sort_order = sort_order
        self.is_expanded = is_expanded
        self.completed_expanded = completed_expanded
        self.deferred_expanded = deferred_expanded
        self.deleted = deleted
        self.deleted_at = deleted_at

    @classmethod
    def from_row(cls, row):
        keys = row.keys()
        return cls(
            id=row["id"],
            name=row["name"],
            sort_order=row["sort_order"],
            is_expanded=bool(row["is_expanded"]),
            completed_expanded=bool(row["completed_expanded"]),
            deferred_expanded=bool(row["deferred_expanded"]) if "deferred_expanded" in keys else False,
            deleted=bool(row["deleted"]),
            deleted_at=row["deleted_at"],
        )


class TaskStore:
    """SQLite 任务存储：分组、任务、排序、归档记录与旧 JSON 迁移。

    归档在数据层用 deleted 标记表达（软删除），永久删除才真正移除行。
    """

    def __init__(self, path):
        self.path = Path(path)
        self.load_warning = None
        self.corrupt_backup_path = None
        self._initialize()

    @staticmethod
    def _now():
        return datetime.now().isoformat()

    @property
    def legacy_json_path(self):
        """仅数据库文件迁移同目录的旧 tasks.json，避免将测试 DB 自身误判。"""
        return self.path.with_name("tasks.json") if self.path.suffix == ".db" else None

    @contextmanager
    def _connection(self):
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        try:
            connection.execute("PRAGMA foreign_keys = ON")
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def _initialize(self):
        self.load_warning = None
        self.corrupt_backup_path = None
        is_new = not self.path.exists()
        if not is_new:
            try:
                with self._connection() as connection:
                    self._create_schema(connection)
                    self._validate_database(connection)
            except (OSError, sqlite3.DatabaseError) as exc:
                self._quarantine_corrupt_file(f"数据库无法读取：{exc}")
                return
        else:
            try:
                self.path.parent.mkdir(parents=True, exist_ok=True)
                with self._connection() as connection:
                    self._create_schema(connection)
                if self.legacy_json_path is not None and self.legacy_json_path.exists():
                    self._migrate_legacy_json()
            except (OSError, sqlite3.DatabaseError) as exc:
                self.load_warning = f"数据库初始化失败：{exc}"

    @staticmethod
    def _create_schema(connection):
        connection.executescript("""
            CREATE TABLE IF NOT EXISTS groups (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                sort_order INTEGER NOT NULL,
                is_expanded INTEGER NOT NULL DEFAULT 1,
                completed_expanded INTEGER NOT NULL DEFAULT 0,
                deleted INTEGER NOT NULL DEFAULT 0,
                deleted_at TEXT
            );

            CREATE TABLE IF NOT EXISTS tasks (
                id TEXT PRIMARY KEY,
                text TEXT NOT NULL DEFAULT '',
                group_id TEXT NOT NULL,
                sort_order INTEGER NOT NULL,
                completed INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                completed_at TEXT,
                deleted INTEGER NOT NULL DEFAULT 0,
                deleted_at TEXT,
                FOREIGN KEY(group_id) REFERENCES groups(id)
            );

            CREATE INDEX IF NOT EXISTS idx_groups_active_order
                ON groups(deleted, sort_order);
            CREATE INDEX IF NOT EXISTS idx_tasks_group_state_order
                ON tasks(group_id, deleted, completed, sort_order);
            CREATE INDEX IF NOT EXISTS idx_tasks_deleted_time
                ON tasks(deleted, deleted_at);
        """)
        group_columns = {
            row["name"] for row in connection.execute("PRAGMA table_info(groups)")
        }
        if "deferred_expanded" not in group_columns:
            connection.execute(
                "ALTER TABLE groups ADD COLUMN deferred_expanded INTEGER NOT NULL DEFAULT 0"
            )
        task_columns = {
            row["name"] for row in connection.execute("PRAGMA table_info(tasks)")
        }
        if "state" not in task_columns:
            connection.execute(
                "ALTER TABLE tasks ADD COLUMN state TEXT NOT NULL DEFAULT 'active'"
            )
            connection.execute(
                "UPDATE tasks SET state = 'completed' WHERE completed = 1"
            )
        if "state_changed_at" not in task_columns:
            connection.execute("ALTER TABLE tasks ADD COLUMN state_changed_at TEXT")
        connection.execute(
            """CREATE INDEX IF NOT EXISTS idx_tasks_group_status_order
               ON tasks(group_id, deleted, state, sort_order)"""
        )

    @staticmethod
    def _validate_database(connection):
        required = {"groups", "tasks"}
        found = {
            row["name"] for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'",
            )
        }
        if not required.issubset(found):
            raise sqlite3.DatabaseError("数据库表结构不完整")
        connection.execute("SELECT count(*) FROM groups").fetchone()
        connection.execute("SELECT count(*) FROM tasks").fetchone()

    def _migrate_legacy_json(self):
        try:
            raw = self.legacy_json_path.read_text(encoding="utf-8")
            data = json.loads(raw)
        except OSError as exc:
            self.load_warning = f"旧任务文件读取失败：{exc}"
            return
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            self._quarantine_legacy_json(f"旧任务文件无法解析：{exc}")
            return
        if not isinstance(data, list):
            self._quarantine_legacy_json("旧任务文件格式错误：顶层内容必须是列表")
            return

        valid = []
        for index, item in enumerate(data):
            if not isinstance(item, dict) or not isinstance(item.get("id"), str):
                continue
            valid.append((index, item))

        try:
            with self._connection() as connection:
                # 新库未迁移前不应有用户数据；否则保留数据库并不删除旧 JSON。
                if connection.execute("SELECT count(*) FROM groups").fetchone()[0]:
                    return
                group_id = str(uuid.uuid4())
                connection.execute(
                    """INSERT INTO groups (
                        id, name, sort_order, is_expanded, completed_expanded,
                        deleted, deleted_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (group_id, "Default", 0, 1, 0, 0, None),
                )
                for index, item in valid:
                    completed = bool(item.get("completed", False))
                    state = "completed" if completed else "active"
                    connection.execute(
                        """INSERT INTO tasks (
                            id, text, group_id, sort_order, completed, created_at,
                            completed_at, deleted, deleted_at, state, state_changed_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                        (
                            item["id"], item.get("text", ""), group_id, index,
                            int(completed), item.get("created_at") or self._now(),
                            item.get("completed_at"),
                            int(bool(item.get("deleted", False))),
                            item.get("deleted_at"), state,
                            item.get("completed_at") if completed else None,
                        ),
                    )
                count = connection.execute("SELECT count(*) FROM tasks").fetchone()[0]
                if count != len(valid):
                    raise sqlite3.DatabaseError("旧任务迁移校验失败")
            self.legacy_json_path.unlink()
        except (OSError, sqlite3.DatabaseError) as exc:
            self.load_warning = f"旧任务迁移失败：{exc}"

    def _quarantine_corrupt_file(self, reason):
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
        backup = self.path.with_name(f"{self.path.name}.corrupt-{stamp}")
        try:
            os.replace(self.path, backup)
        except OSError as exc:
            self.load_warning = f"{reason}；损坏数据库备份失败：{exc}"
            return
        self.corrupt_backup_path = backup
        self.load_warning = f"{reason}；原数据库已备份到：{backup}"

    def _quarantine_legacy_json(self, reason):
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
        backup = self.legacy_json_path.with_name(
            f"{self.legacy_json_path.name}.corrupt-{stamp}",
        )
        try:
            os.replace(self.legacy_json_path, backup)
        except OSError as exc:
            self.load_warning = f"{reason}；损坏旧任务文件备份失败：{exc}"
            return
        self.corrupt_backup_path = backup
        self.load_warning = f"{reason}；原文件已备份到：{backup}"

    # ---- 查询 ----
    def groups(self, include_deleted=False):
        where = "" if include_deleted else "WHERE deleted = 0"
        with self._connection() as connection:
            rows = connection.execute(
                f"SELECT * FROM groups {where} ORDER BY sort_order, id",
            ).fetchall()
        return [TaskGroup.from_row(row) for row in rows]

    def get_group(self, group_id):
        with self._connection() as connection:
            row = connection.execute(
                "SELECT * FROM groups WHERE id = ?", (group_id,),
            ).fetchone()
        return TaskGroup.from_row(row) if row is not None else None

    def get(self, task_id):
        with self._connection() as connection:
            row = connection.execute(
                "SELECT * FROM tasks WHERE id = ?", (task_id,),
            ).fetchone()
        return Task.from_row(row) if row is not None else None

    def active_tasks(self, group_id=None):
        return self._tasks_by_state("active", group_id, "sort_order, id")

    def completed_tasks(self, group_id=None):
        return self._tasks_by_state(
            "completed", group_id,
            "state_changed_at DESC, completed_at DESC, created_at DESC, id",
        )

    def deferred_tasks(self, group_id=None):
        return self._tasks_by_state(
            "deferred", group_id, "state_changed_at DESC, created_at DESC, id",
        )

    def _tasks_by_state(self, state, group_id, order_by):
        params = [state]
        where = "WHERE deleted = 0 AND state = ?"
        if group_id is not None:
            where += " AND group_id = ?"
            params.append(group_id)
        with self._connection() as connection:
            rows = connection.execute(
                f"SELECT * FROM tasks {where} ORDER BY {order_by}", params,
            ).fetchall()
        return [Task.from_row(row) for row in rows]

    def deleted_tasks_by_group(self):
        with self._connection() as connection:
            rows = connection.execute("""
                SELECT tasks.*, groups.name AS group_name, groups.deleted AS group_deleted
                FROM tasks JOIN groups ON groups.id = tasks.group_id
                WHERE tasks.deleted = 1
                ORDER BY groups.sort_order, groups.id, tasks.deleted_at DESC, tasks.id
            """).fetchall()
        grouped = {}
        for row in rows:
            group_id = row["group_id"]
            if group_id not in grouped:
                grouped[group_id] = {
                    "group": TaskGroup.from_row({
                        "id": group_id,
                        "name": row["group_name"],
                        "sort_order": 0,
                        "is_expanded": 1,
                        "completed_expanded": 0,
                        "deleted": row["group_deleted"],
                        "deleted_at": None,
                    }),
                    "tasks": [],
                }
            grouped[group_id]["tasks"].append(Task.from_row(row))
        return list(grouped.values())

    def deleted_tasks(self):
        return [
            task for entry in self.deleted_tasks_by_group()
            for task in entry["tasks"]
        ]

    # Compatibility name retained for integrations that used the previous model.
    def history_tasks(self):
        return self.deleted_tasks()

    def group_task_count(self, group_id, include_deleted=False):
        where = "group_id = ?"
        if not include_deleted:
            where += " AND deleted = 0"
        with self._connection() as connection:
            return connection.execute(
                f"SELECT count(*) FROM tasks WHERE {where}", (group_id,),
            ).fetchone()[0]

    # ---- 分组变更 ----
    def create_group(self, name):
        name = str(name).strip()
        if not name:
            raise ValueError("分组名称不能为空")
        group = TaskGroup(str(uuid.uuid4()), name)
        with self._connection() as connection:
            group.sort_order = connection.execute(
                "SELECT COALESCE(MAX(sort_order), -1) + 1 FROM groups WHERE deleted = 0",
            ).fetchone()[0]
            connection.execute(
                """INSERT INTO groups (
                    id, name, sort_order, is_expanded, completed_expanded,
                    deleted, deleted_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (group.id, group.name, group.sort_order, 1, 0, 0, None),
            )
        return group

    def rename_group(self, group_id, name):
        name = str(name).strip()
        if not name:
            raise ValueError("分组名称不能为空")
        with self._connection() as connection:
            connection.execute("UPDATE groups SET name = ? WHERE id = ?", (name, group_id))
        return self.get_group(group_id)

    def set_group_expanded(self, group_id, expanded):
        with self._connection() as connection:
            connection.execute(
                "UPDATE groups SET is_expanded = ? WHERE id = ?",
                (int(bool(expanded)), group_id),
            )

    def set_completed_expanded(self, group_id, expanded):
        self._set_group_list_expanded(group_id, "completed_expanded", expanded)

    def set_deferred_expanded(self, group_id, expanded):
        self._set_group_list_expanded(group_id, "deferred_expanded", expanded)

    def _set_group_list_expanded(self, group_id, column, expanded):
        if column not in {"completed_expanded", "deferred_expanded"}:
            raise ValueError("未知的分组折叠状态")
        with self._connection() as connection:
            connection.execute(
                f"UPDATE groups SET {column} = ? WHERE id = ?",
                (int(bool(expanded)), group_id),
            )

    def reorder_groups(self, group_ids):
        current = [group.id for group in self.groups()]
        ordered = list(group_ids)
        if len(ordered) != len(current) or set(ordered) != set(current) or ordered == current:
            return False
        with self._connection() as connection:
            connection.executemany(
                "UPDATE groups SET sort_order = ? WHERE id = ?",
                ((index, group_id) for index, group_id in enumerate(ordered)),
            )
        return True

    def delete_group(self, group_id):
        group = self.get_group(group_id)
        if group is None or group.deleted:
            return None
        stamp = self._now()
        with self._connection() as connection:
            connection.execute(
                "UPDATE groups SET deleted = 1, deleted_at = ? WHERE id = ?",
                (stamp, group_id),
            )
            connection.execute(
                "UPDATE tasks SET deleted = 1, deleted_at = ? WHERE group_id = ?",
                (stamp, group_id),
            )
        group.deleted = True
        group.deleted_at = stamp
        return group

    def _restore_group_if_deleted(self, connection, group_id):
        connection.execute(
            "UPDATE groups SET deleted = 0, deleted_at = NULL WHERE id = ? AND deleted = 1",
            (group_id,),
        )

    # ---- 任务变更 ----
    def _default_group_id(self):
        groups = self.groups()
        if groups:
            return groups[0].id
        return self.create_group("Default").id

    def add(self, group_id, text=None):
        # 兼容旧调用 add("任务文本"):自动使用第一个分组。
        if text is None:
            text = group_id
            group_id = self._default_group_id()
        if self.get_group(group_id) is None:
            raise ValueError("分组不存在")
        task = Task(str(uuid.uuid4()), text, group_id)
        with self._connection() as connection:
            task.sort_order = connection.execute(
                """SELECT COALESCE(MAX(sort_order), -1) + 1 FROM tasks
                   WHERE group_id = ? AND deleted = 0 AND state = 'active'""",
                (group_id,),
            ).fetchone()[0]
            connection.execute(
                """INSERT INTO tasks (
                    id, text, group_id, sort_order, completed, created_at,
                    completed_at, deleted, deleted_at, state, state_changed_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    task.id, task.text, task.group_id, task.sort_order, 0,
                    task.created_at, None, 0, None, "active", None,
                ),
            )
        return task

    def update_text(self, task_id, text):
        with self._connection() as connection:
            connection.execute("UPDATE tasks SET text = ? WHERE id = ?", (text, task_id))
        return self.get(task_id)

    def reorder_active(self, group_id, task_ids):
        current = [task.id for task in self.active_tasks(group_id)]
        ordered = list(task_ids)
        if len(ordered) != len(current) or set(ordered) != set(current) or ordered == current:
            return False
        with self._connection() as connection:
            connection.executemany(
                "UPDATE tasks SET sort_order = ? WHERE id = ? AND group_id = ?",
                ((index, task_id, group_id) for index, task_id in enumerate(ordered)),
            )
        return True

    def complete(self, task_id):
        return self.set_task_state(task_id, "completed")

    def defer(self, task_id):
        return self.set_task_state(task_id, "deferred")

    def set_task_state(self, task_id, state):
        if state not in {"completed", "deferred"}:
            raise ValueError("未知的任务状态")
        task = self.get(task_id)
        if task is None:
            return None
        stamp = self._now()
        completed_at = stamp if state == "completed" else None
        with self._connection() as connection:
            connection.execute(
                """UPDATE tasks SET state = ?, state_changed_at = ?,
                   completed = ?, completed_at = ?, deleted = 0, deleted_at = NULL
                   WHERE id = ?""",
                (state, stamp, int(state == "completed"), completed_at, task_id),
            )
        return self.get(task_id)

    def restore(self, task_id):
        task = self.get(task_id)
        if task is None:
            return None
        if task.deleted:
            restored = self.restore_many([task_id])
            return restored[0] if restored else None
        if task.state == "active":
            return task
        with self._connection() as connection:
            next_order = connection.execute(
                """SELECT COALESCE(MAX(sort_order), -1) + 1 FROM tasks
                   WHERE group_id = ? AND deleted = 0 AND state = 'active'""",
                (task.group_id,),
            ).fetchone()[0]
            connection.execute(
                """UPDATE tasks SET state = 'active', state_changed_at = NULL,
                   completed = 0, completed_at = NULL, sort_order = ? WHERE id = ?""",
                (next_order, task_id),
            )
        return self.get(task_id)

    def restore_many(self, task_ids):
        ids = list(dict.fromkeys(task_ids))
        if not ids:
            return []
        placeholders = ",".join("?" for _ in ids)
        with self._connection() as connection:
            rows = connection.execute(
                f"SELECT * FROM tasks WHERE id IN ({placeholders}) AND deleted = 1", ids,
            ).fetchall()
            tasks = [Task.from_row(row) for row in rows]
            for group_id in {task.group_id for task in tasks}:
                self._restore_group_if_deleted(connection, group_id)
            for task in tasks:
                next_order = connection.execute(
                    """SELECT COALESCE(MAX(sort_order), -1) + 1 FROM tasks
                       WHERE group_id = ? AND deleted = 0 AND state = 'active'""",
                    (task.group_id,),
                ).fetchone()[0]
                connection.execute(
                    """UPDATE tasks SET deleted = 0, deleted_at = NULL,
                       state = 'active', state_changed_at = NULL, completed = 0,
                       completed_at = NULL, sort_order = ? WHERE id = ?""",
                    (next_order, task.id),
                )
        return [self.get(task.id) for task in tasks]

    def delete(self, task_id):
        task = self.get(task_id)
        if task is None:
            return None
        with self._connection() as connection:
            connection.execute(
                "UPDATE tasks SET deleted = 1, deleted_at = ? WHERE id = ?",
                (self._now(), task_id),
            )
        return self.get(task_id)

    def permanent_delete(self, task_ids):
        ids = list(dict.fromkeys(task_ids))
        if not ids:
            return []
        placeholders = ",".join("?" for _ in ids)
        with self._connection() as connection:
            rows = connection.execute(
                f"SELECT * FROM tasks WHERE id IN ({placeholders})", ids,
            ).fetchall()
            tasks = [Task.from_row(row) for row in rows]
            connection.execute(f"DELETE FROM tasks WHERE id IN ({placeholders})", ids)
            connection.execute("""
                DELETE FROM groups
                WHERE deleted = 1
                  AND NOT EXISTS (SELECT 1 FROM tasks WHERE tasks.group_id = groups.id)
            """)
        return tasks
