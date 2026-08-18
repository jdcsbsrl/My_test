"""审核日志持久化管理器

使用 PostgreSQL 存储审核日志（通过项目统一的 db_pool 连接池）。
支持自动建表、查询、摘要统计和日志清理。
当 PostgreSQL 连接失败时，自动降级到内存存储。
"""

import json
import os
import sqlite3
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import text

from modules.trae_test.utils.runtime_paths import runtime_dir


class AuditLogger:
    """审核日志持久化管理器

    使用项目统一的 PostgreSQL 连接池，依赖连接池 + PG MVCC 处理并发。
    当 PostgreSQL 不可用时，自动降级到 SQLite 内存存储。
    """

    def __init__(self):
        """初始化日志管理器"""
        self._use_pg = True
        try:
            self._init_db()
        except Exception as e:
            self._use_pg = False
            print(f"[AuditLogger] PostgreSQL 连接失败，降级到 SQLite 内存存储: {e}")
            self._init_memory_db()

    def _execute_in_session(self, func):
        """安全执行：自动 rollback + close

        Args:
            func: 接收 session 参数的函数，返回执行结果

        Returns:
            函数执行结果

        Raises:
            Exception: 函数执行过程中抛出的任何异常
        """
        if self._use_pg:
            from modules.trae_test.core.db_pool import get_session

            session = get_session()
            try:
                return func(session)
            except Exception:
                session.rollback()
                raise
            finally:
                session.close()
        else:
            conn = self._get_memory_connection()
            try:
                return func(conn)
            except Exception:
                conn.rollback()
                raise
            finally:
                conn.close()

    def _get_memory_connection(self) -> sqlite3.Connection:
        """获取 SQLite 内存数据库连接"""
        conn = sqlite3.connect(self._memory_db_path, timeout=10)
        self._enable_sqlite_wal(conn)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_memory_db(self):
        """初始化 SQLite 内存数据库（降级方案）"""
        runtime_root = runtime_dir("logs") / "audit"
        worker_id = os.getenv("PYTEST_XDIST_WORKER")
        db_name = f"audit_history_{worker_id}.db" if worker_id else "audit_history.db"
        self._memory_db_path = str(runtime_root / db_name)
        runtime_root.mkdir(parents=True, exist_ok=True)

        conn = sqlite3.connect(self._memory_db_path, timeout=10)
        self._enable_sqlite_wal(conn)
        try:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS audit_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    audit_type TEXT,
                    passed INTEGER NOT NULL,
                    score REAL,
                    execution_time REAL,
                    error_count INTEGER DEFAULT 0,
                    warning_count INTEGER DEFAULT 0,
                    manual_review_count INTEGER DEFAULT 0,
                    issues_json TEXT,
                    suggestions_json TEXT,
                    context_json TEXT,
                    created_at TEXT DEFAULT (datetime('now', 'localtime'))
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_audit_logs_timestamp ON audit_logs(timestamp)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_audit_logs_type ON audit_logs(audit_type)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_audit_logs_passed ON audit_logs(passed)")
            conn.commit()
        finally:
            conn.close()

    @staticmethod
    def _enable_sqlite_wal(conn: sqlite3.Connection) -> None:
        try:
            conn.execute("PRAGMA journal_mode=WAL")
        except sqlite3.OperationalError:
            pass

    def _init_db(self):
        """初始化数据库表结构和索引"""

        def create_tables(session):
            session.execute(text("""
                CREATE TABLE IF NOT EXISTS audit_logs (
                    id SERIAL PRIMARY KEY,
                    timestamp TEXT NOT NULL,
                    audit_type TEXT,
                    passed BOOLEAN NOT NULL,
                    score REAL,
                    execution_time REAL,
                    error_count INTEGER DEFAULT 0,
                    warning_count INTEGER DEFAULT 0,
                    manual_review_count INTEGER DEFAULT 0,
                    issues_json TEXT,
                    suggestions_json TEXT,
                    context_json TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """))

            session.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_audit_logs_timestamp ON audit_logs(timestamp)
            """))
            session.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_audit_logs_type ON audit_logs(audit_type)
            """))
            session.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_audit_logs_passed ON audit_logs(passed)
            """))

            session.commit()

        self._execute_in_session(create_tables)

    def log(self, audit_result: Any, context: dict = None) -> int:
        """记录一条审核日志

        Args:
            audit_result: AuditResult 对象（或任何有 to_dict()/to_storage_dict() 的对象）
            context: 审核上下文

        Returns:
            int: 日志记录的 ID
        """
        if hasattr(audit_result, "to_storage_dict"):
            storage = audit_result.to_storage_dict()
        elif hasattr(audit_result, "to_dict"):
            storage = audit_result.to_dict()
        elif isinstance(audit_result, dict):
            storage = audit_result
        else:
            storage = {"passed": False, "errors": [], "warnings": [], "suggestions": []}

        context = context or {}

        def do_log(session):
            timestamp = storage.get("timestamp", datetime.now().isoformat())
            audit_type = storage.get("audit_type", "")
            passed = storage.get("passed", False)
            score = storage.get("score", None)
            execution_time = storage.get("execution_time", 0.0)
            error_count = storage.get("error_count", len(storage.get("errors", [])))
            warning_count = storage.get("warning_count", len(storage.get("warnings", [])))

            issues = storage.get("issues", [])
            if not issues:
                issues = storage.get("errors", []) + storage.get("warnings", [])

            issues_json = json.dumps(issues, ensure_ascii=False, default=str)
            suggestions_json = json.dumps(storage.get("suggestions", []), ensure_ascii=False, default=str)
            context_json = json.dumps(context, ensure_ascii=False, default=str)

            if self._use_pg:
                result = session.execute(text("""
                    INSERT INTO audit_logs (
                        timestamp, audit_type, passed, score, execution_time,
                        error_count, warning_count, issues_json, suggestions_json, context_json
                    ) VALUES (
                        :timestamp, :audit_type, :passed, :score, :execution_time,
                        :error_count, :warning_count, :issues_json, :suggestions_json, :context_json
                    ) RETURNING id
                """), {
                    "timestamp": timestamp,
                    "audit_type": audit_type,
                    "passed": passed,
                    "score": score,
                    "execution_time": execution_time,
                    "error_count": error_count,
                    "warning_count": warning_count,
                    "issues_json": issues_json,
                    "suggestions_json": suggestions_json,
                    "context_json": context_json,
                })
                session.commit()
                return result.scalar()
            else:
                cursor = session.execute(
                    """
                    INSERT INTO audit_logs
                        (timestamp, audit_type, passed, score, execution_time,
                         error_count, warning_count, issues_json, suggestions_json, context_json)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        timestamp,
                        audit_type,
                        1 if passed else 0,
                        score,
                        execution_time,
                        error_count,
                        warning_count,
                        issues_json,
                        suggestions_json,
                        context_json,
                    ),
                )
                session.commit()
                return cursor.lastrowid

        return self._execute_in_session(do_log)

    def query(
        self,
        start_time: str | None = None,
        end_time: str | None = None,
        audit_type: str | None = None,
        passed: bool | None = None,
        issue_category: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[dict]:
        """查询审核历史

        支持按时间范围、审核类型、通过/失败、问题分类过滤。

        Args:
            start_time: 起始时间（ISO 格式或 'YYYY-MM-DD'）
            end_time: 结束时间
            audit_type: 审核类型筛选
            passed: 通过/失败筛选
            issue_category: 问题分类关键词（在 issues_json 中模糊搜索）
            limit: 返回记录数上限，默认 100
            offset: 偏移量，默认 0

        Returns:
            list[dict]: 审核日志列表
        """
        conditions = []
        params: dict[str, Any] = {}

        if start_time:
            conditions.append("timestamp >= :start_time")
            params["start_time"] = start_time
        if end_time:
            conditions.append("timestamp <= :end_time")
            params["end_time"] = end_time
        if audit_type:
            conditions.append("audit_type = :audit_type")
            params["audit_type"] = audit_type
        if passed is not None:
            conditions.append("passed = :passed")
            params["passed"] = passed
        if issue_category:
            conditions.append("issues_json LIKE :issue_category")
            params["issue_category"] = f"%{issue_category}%"

        where_clause = " AND ".join(conditions) if conditions else "1=1"

        def do_query(session):
            if self._use_pg:
                sql = f"SELECT * FROM audit_logs WHERE {where_clause} ORDER BY timestamp DESC LIMIT :limit OFFSET :offset"
                pg_params = params.copy()
                pg_params["limit"] = limit
                pg_params["offset"] = offset
                rows = session.execute(text(sql), pg_params).fetchall()
            else:
                sql = f"SELECT * FROM audit_logs WHERE {where_clause} ORDER BY timestamp DESC LIMIT {limit} OFFSET {offset}"
                sqlite_params = list(params.values())
                sqlite_sql = sql.replace(":", "?")
                rows = session.execute(sqlite_sql, sqlite_params).fetchall()
            return [self._row_to_dict(row) for row in rows]

        return self._execute_in_session(do_query)

    def get_summary(self, days: int = 7) -> dict:
        """获取审核摘要统计

        返回指定天数的审核总数、通过率、问题分类分布等。

        Args:
            days: 统计天数，默认 7 天

        Returns:
            dict: 审核摘要统计
        """
        since = (datetime.now() - timedelta(days=days)).isoformat()

        def do_summary(session):
            if self._use_pg:
                total = session.execute(
                    text("SELECT COUNT(*) FROM audit_logs WHERE timestamp >= :since"),
                    {"since": since}
                ).scalar()
            else:
                total = session.execute(
                    "SELECT COUNT(*) FROM audit_logs WHERE timestamp >= ?", (since,)
                ).fetchone()[0]

            if total == 0:
                return {
                    "total": 0,
                    "passed": 0,
                    "failed": 0,
                    "pass_rate": 0.0,
                    "avg_execution_time": 0.0,
                    "total_errors": 0,
                    "total_warnings": 0,
                    "type_distribution": {},
                    "days": days,
                }

            if self._use_pg:
                passed = session.execute(
                    text("SELECT COUNT(*) FROM audit_logs WHERE timestamp >= :since AND passed = true"),
                    {"since": since}
                ).scalar()

                avg_time = session.execute(
                    text("SELECT AVG(execution_time) FROM audit_logs WHERE timestamp >= :since"),
                    {"since": since}
                ).scalar() or 0.0

                error_stats = session.execute(
                    text("SELECT SUM(error_count), SUM(warning_count) FROM audit_logs WHERE timestamp >= :since"),
                    {"since": since}
                ).fetchone()
                total_errors = error_stats[0] or 0
                total_warnings = error_stats[1] or 0

                type_rows = session.execute(
                    text("SELECT audit_type, COUNT(*) as cnt FROM audit_logs WHERE timestamp >= :since GROUP BY audit_type"),
                    {"since": since}
                ).fetchall()
                type_distribution = {row[0]: row[1] for row in type_rows}
            else:
                passed = session.execute(
                    "SELECT COUNT(*) FROM audit_logs WHERE timestamp >= ? AND passed = 1", (since,)
                ).fetchone()[0]

                avg_time = session.execute(
                    "SELECT AVG(execution_time) FROM audit_logs WHERE timestamp >= ?", (since,)
                ).fetchone()[0] or 0.0

                error_stats = session.execute(
                    "SELECT SUM(error_count), SUM(warning_count) FROM audit_logs WHERE timestamp >= ?",
                    (since,),
                ).fetchone()
                total_errors = error_stats[0] or 0
                total_warnings = error_stats[1] or 0

                type_rows = session.execute(
                    "SELECT audit_type, COUNT(*) as cnt FROM audit_logs WHERE timestamp >= ? GROUP BY audit_type",
                    (since,),
                ).fetchall()
                type_distribution = {row["audit_type"]: row["cnt"] for row in type_rows}

            return {
                "total": total,
                "passed": passed,
                "failed": total - passed,
                "pass_rate": round(passed / total * 100, 2) if total > 0 else 0.0,
                "avg_execution_time": round(avg_time, 4),
                "total_errors": total_errors,
                "total_warnings": total_warnings,
                "type_distribution": type_distribution,
                "days": days,
            }

        return self._execute_in_session(do_summary)

    def cleanup(self, retention_days: int = 90):
        """清理超过保留期限的日志

        Args:
            retention_days: 保留天数，默认 90 天
        """
        cutoff = (datetime.now() - timedelta(days=retention_days)).isoformat()

        def do_cleanup(session):
            if self._use_pg:
                result = session.execute(
                    text("DELETE FROM audit_logs WHERE timestamp < :cutoff"),
                    {"cutoff": cutoff}
                )
                deleted = result.rowcount
            else:
                cursor = session.execute("DELETE FROM audit_logs WHERE timestamp < ?", (cutoff,))
                deleted = cursor.rowcount
            session.commit()
            if deleted > 0:
                if not self._use_pg:
                    session.execute("VACUUM")
                print(f"[AuditLogger] 已清理 {deleted} 条超过 {retention_days} 天的审核日志")
            return deleted

        return self._execute_in_session(do_cleanup)

    def get_by_id(self, log_id: int) -> dict | None:
        """根据 ID 获取单条审核日志

        Args:
            log_id: 日志 ID

        Returns:
            dict | None: 审核日志，不存在则返回 None
        """

        def do_get(session):
            if self._use_pg:
                row = session.execute(
                    text("SELECT * FROM audit_logs WHERE id = :log_id"),
                    {"log_id": log_id}
                ).fetchone()
            else:
                row = session.execute("SELECT * FROM audit_logs WHERE id = ?", (log_id,)).fetchone()
            return self._row_to_dict(row) if row else None

        return self._execute_in_session(do_get)

    def get_recent(self, limit: int = 20, audit_type: str | None = None) -> list[dict]:
        """获取最近的审核日志

        Args:
            limit: 返回记录数上限，默认 20
            audit_type: 可选的审核类型筛选

        Returns:
            list[dict]: 最近的审核日志列表
        """
        return self.query(audit_type=audit_type, limit=limit)

    @staticmethod
    def _row_to_dict(row) -> dict:
        """将数据库行转换为字典，并反序列化 JSON 字段

        Args:
            row: SQLAlchemy Row 或 sqlite3.Row 对象

        Returns:
            dict: 包含反序列化后的数据的字典
        """
        if row is None:
            return None

        if isinstance(row, sqlite3.Row):
            result = {key: row[key] for key in row.keys()}
        elif hasattr(row, "_mapping"):
            result = dict(row._mapping)
        else:
            result = dict(row)

        for json_field in ("issues_json", "suggestions_json", "context_json"):
            raw = result.get(json_field)
            if raw:
                try:
                    result[json_field.replace("_json", "")] = json.loads(raw)
                except (json.JSONDecodeError, TypeError):
                    result[json_field.replace("_json", "")] = raw
            else:
                result[json_field.replace("_json", "")] = []
            del result[json_field]

        if "passed" in result:
            result["passed"] = bool(result["passed"])

        return result
