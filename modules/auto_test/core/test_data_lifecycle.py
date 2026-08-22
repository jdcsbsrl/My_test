"""测试数据生命周期管理器 - 测试数据准备与清理工具

核心功能：
- 支持测试前数据自动准备和环境初始化
- 实现测试后数据自动清理和环境恢复
- 提供数据准备/清理失败的重试机制和异常处理
- 支持多环境（开发、测试、预生产）的数据管理策略
- 级联删除策略（基于Kahn拓扑排序，含环检测）
- 兜底清理机制（API失败→DB直连）
"""

import logging
import json
import os
import re
import time
import uuid
from collections import deque
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Any

from modules.auto_test.core.db_helper import DBHelper
from modules.trae_test.utils.runtime_paths import runtime_dir

logger = logging.getLogger(__name__)


class CleanupFailureError(RuntimeError):
    """Raised when one or more cleanup operations are not confirmed successful."""


class CleanupOwnershipError(ValueError):
    """Raised when a cleanup target is not owned by the current test run."""


def _safe_runtime_component(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_.-]+", "_", value).strip("._")
    return cleaned or "unknown"


def _cleanup_failure_path(
    run_id: str | None = None,
    worker_id: str | None = None,
    tenant_id: str | None = None,
) -> Path:
    run_id = _safe_runtime_component(run_id or os.getenv("TEST_RUN_ID", "local"))
    worker_id = _safe_runtime_component(worker_id or os.getenv("PYTEST_XDIST_WORKER", "master"))
    tenant_id = _safe_runtime_component(
        tenant_id
        or os.getenv("TEST_TENANT_ID")
        or os.getenv("AUTO_TEST_TENANT_ID")
        or os.getenv("TENANT_ID")
        or "000000"
    )
    report_dir = runtime_dir("reports") / "runs" / run_id / worker_id / tenant_id
    report_dir.mkdir(parents=True, exist_ok=True)
    return report_dir / "cleanup-failures.jsonl"


class TestDataLifecycleManager:
    """测试数据生命周期管理器（含级联删除策略和兜底清理机制）"""

    # 数据类型的数据库表映射（用于DB兜底清理）
    TABLE_MAP = {
        "order": "sales_order",
        "delivery": "delivery_order",
        "invoice": "invoice",
        "inventory": "oms_inventory",
        "sku": "oms_sku",
    }

    def __init__(
        self,
        env: str = "test",
        *,
        run_id: str | None = None,
        worker_id: str | None = None,
        tenant_id: str | None = None,
    ):
        self.env = str(env or "").strip().lower()
        self.run_id = run_id or os.getenv("TEST_RUN_ID") or uuid.uuid4().hex
        self.worker_id = worker_id or os.getenv("PYTEST_XDIST_WORKER") or "master"
        self.tenant_id = (
            tenant_id
            or os.getenv("TEST_TENANT_ID")
            or os.getenv("AUTO_TEST_TENANT_ID")
            or os.getenv("TENANT_ID")
            or "000000"
        )
        self._setup_tasks: list[tuple] = []
        self._cleanup_tasks: list[dict[str, Any]] = []
        self._retry_config = {
            "max_retries": 3,
            "retry_delay": 2,  # seconds
        }
        # 依赖关系图（用于拓扑排序）
        self._dependency_graph: dict[str, list[str]] = {}
        # 已创建的测试数据记录（用于清理）
        self._created_data: list[dict[str, Any]] = []
        self._cleanup_failures: list[dict[str, Any]] = []
        # DB 兜底只允许项目认可的测试环境，未知环境默认关闭。
        self._enable_db_fallback = self.env in {"test", "test_env", "uat"}
        self.db_helper = DBHelper(env=self.env) if self._enable_db_fallback else None

    def register_setup_task(
        self,
        task: Callable,
        *args,
        dependencies: list[str] | None = None,
        task_name: str | None = None,
        **kwargs,
    ) -> None:
        """注册数据准备任务

        Args:
            task: 准备任务函数
            dependencies: 依赖的其他任务名称列表
            task_name: 任务名称（用于依赖关系标识），默认自动生成
        """
        if task_name is None:
            task_name = f"task_{len(self._setup_tasks)}"
        self._setup_tasks.append((task_name, task, args, kwargs))

        # 注册依赖关系
        if dependencies:
            self._dependency_graph[task_name] = dependencies

    def register_cleanup_task(
        self,
        task: Callable,
        *args,
        fallback: Callable | None = None,
        data_type: str | None = None,
        data_id: str | None = None,
        owner_run_id: str | None = None,
        owner_worker_id: str | None = None,
        owner_tenant_id: str | None = None,
        worker_id: str | None = None,
        tenant_id: str | None = None,
        **kwargs,
    ) -> None:
        """注册数据清理任务

        Args:
            task: 清理任务函数（通常是API删除）
            fallback: 兜底清理任务（DB直连硬删除，仅限测试环境）
            data_type: 兜底清理对应的白名单数据类型
            data_id: 兜底清理对应的数据主键
            owner_run_id: 数据所属测试运行ID，必须与当前运行一致
        """
        target_run_id = self.run_id if owner_run_id is None else owner_run_id
        target_worker_id = (
            self.worker_id if owner_worker_id is None and worker_id is None else owner_worker_id or worker_id
        )
        target_tenant_id = (
            self.tenant_id if owner_tenant_id is None and tenant_id is None else owner_tenant_id or tenant_id
        )
        target = {
            "type": data_type,
            "id": data_id,
            "run_id": target_run_id,
            "worker_id": target_worker_id,
            "tenant_id": target_tenant_id,
        }
        if fallback is not None:
            self._validate_owned_target(target)
        self._cleanup_tasks.append(
            {
                "task": task,
                "args": args,
                "kwargs": kwargs,
                "fallback": fallback,
                **target,
            }
        )

    def register_created_data(
        self,
        data_type: str,
        data_id: str,
        cleanup_func: Callable,
        *,
        owner_run_id: str | None = None,
        owner_worker_id: str | None = None,
        owner_tenant_id: str | None = None,
        run_id: str | None = None,
        worker_id: str | None = None,
        tenant_id: str | None = None,
    ) -> None:
        """注册已创建的测试数据，便于后续清理

        Args:
            data_type: 数据类型（如 order, delivery, invoice）
            data_id: 数据ID
            cleanup_func: 清理函数
        """
        data_item = {
            "type": data_type,
            "id": data_id,
            "cleanup": cleanup_func,
            "created_at": datetime.now(),
            "run_id": owner_run_id or run_id or self.run_id,
            "worker_id": owner_worker_id or worker_id or self.worker_id,
            "tenant_id": owner_tenant_id or tenant_id or self.tenant_id,
        }
        self._validate_owned_target(data_item)
        self._created_data.append(data_item)

    def execute_setup(self) -> None:
        """执行所有数据准备任务（按依赖顺序）"""
        if not self._setup_tasks:
            logger.info("No setup tasks registered, skipping setup phase")
            return

        # 拓扑排序任务执行顺序
        execution_order = self._topological_sort()

        for task_name in execution_order:
            for name, task, args, kwargs in self._setup_tasks:
                if name == task_name:
                    self._execute_with_retry(task, *args, **kwargs)
                    break

    def execute_cleanup(self) -> None:
        """执行所有数据清理任务（按拓扑排序逆序）"""
        if not self._cleanup_tasks and not self._created_data:
            logger.info("No cleanup tasks registered, skipping cleanup phase")
            return

        # 获取清理顺序（依赖逆序）
        cleanup_order = self._get_cleanup_order()

        for item in cleanup_order:
            try:
                if isinstance(item, dict) and "task" in item:
                    # 执行普通清理任务
                    self._execute_cleanup_task(item)
                else:
                    # 执行已创建数据的清理
                    self._execute_data_cleanup(item)
            except Exception as unexpected_error:
                # A broken reporter or unexpected callback must not skip the
                # remaining cleanup items; the final aggregate error still blocks.
                self._record_cleanup_failure(item, unexpected_error, None)
                logger.exception("Unexpected cleanup failure")
        if self._cleanup_failures:
            raise CleanupFailureError(
                f"{len(self._cleanup_failures)} cleanup operation(s) were not confirmed successful"
            )

    def _execute_cleanup_task(self, cleanup_item: dict[str, Any]) -> None:
        """执行单个清理任务（含兜底机制）"""
        task = cleanup_item["task"]
        args = cleanup_item["args"]
        kwargs = cleanup_item["kwargs"]
        fallback = cleanup_item.get("fallback")

        try:
            result = task(*args, **kwargs)
            if result is False:
                raise RuntimeError("API cleanup returned False")
        except Exception as api_error:
            logger.warning(f"API cleanup failed: {api_error}")

            # 尝试兜底清理（DB直连）
            if fallback and self._enable_db_fallback:
                try:
                    self._validate_owned_target(cleanup_item)
                    result = fallback(*args, **kwargs)
                    if result is False:
                        raise RuntimeError("DB fallback cleanup returned False")
                    logger.info("Fallback cleanup (DB) succeeded")
                except Exception as db_error:
                    logger.error(f"Both API and DB cleanup failed: {db_error}")
                    self._record_cleanup_failure(cleanup_item, api_error, db_error)
                    self._log_cleanup_failure(cleanup_item, str(api_error), str(db_error))
            else:
                fallback_error = None
                if fallback and not self._enable_db_fallback:
                    fallback_error = CleanupOwnershipError(
                        f"DB fallback is disabled for environment {self.env!r}"
                    )
                self._record_cleanup_failure(cleanup_item, api_error, fallback_error)
                self._log_cleanup_failure(
                    cleanup_item,
                    str(api_error),
                    str(fallback_error) if fallback_error else None,
                )

    def _execute_data_cleanup(self, data_item: dict[str, Any]) -> None:
        """执行已创建数据的清理"""
        try:
            result = data_item["cleanup"]()
            if result is False:
                raise RuntimeError("API cleanup returned False")
        except Exception as e:
            logger.warning(f"Data cleanup failed for {data_item['type']}:{data_item['id']}: {e}")
            # 尝试DB兜底清理
            try:
                if not self._enable_db_fallback:
                    raise CleanupOwnershipError(f"DB fallback is disabled for environment {self.env!r}")
                self._db_fallback_cleanup(data_item)
            except Exception as fallback_error:
                self._record_cleanup_failure(data_item, e, fallback_error)
                self._log_cleanup_failure(data_item, str(e), str(fallback_error))

    def _record_cleanup_failure(self, item: Any, api_error: Exception, db_error: Exception | None) -> None:
        """Persist a local fallback record even when the database is unavailable."""
        failure = {
            "run_id": self.run_id,
            "worker_id": self.worker_id,
            "tenant_id": self.tenant_id,
            "environment": self.env,
            "item": str(item),
            "api_error": str(api_error),
            "db_error": str(db_error) if db_error else None,
            "created_at": datetime.now().isoformat(),
        }
        self._cleanup_failures.append(failure)
        try:
            with _cleanup_failure_path(self.run_id, self.worker_id, self.tenant_id).open(
                "a", encoding="utf-8"
            ) as stream:
                stream.write(json.dumps(failure, ensure_ascii=False) + "\n")
        except Exception:
            logger.exception("Failed to persist cleanup failure locally")

    @property
    def cleanup_failures(self) -> list[dict[str, Any]]:
        return list(self._cleanup_failures)

    def _validate_owned_target(self, data_item: dict[str, Any]) -> None:
        owner_run_id = data_item.get("run_id")
        if owner_run_id != self.run_id:
            raise CleanupOwnershipError(
                f"Cleanup target belongs to run {owner_run_id!r}, not current run {self.run_id!r}"
            )
        for field, current_value in (
            ("worker_id", self.worker_id),
            ("tenant_id", self.tenant_id),
        ):
            if data_item.get(field) != current_value:
                raise CleanupOwnershipError(
                    f"Cleanup target {field} {data_item.get(field)!r} does not match current {current_value!r}"
                )
        data_type = data_item.get("type")
        if data_type not in self.TABLE_MAP:
            raise CleanupOwnershipError(f"Unsupported cleanup data type: {data_type!r}")
        data_id = data_item.get("id")
        if data_id is None or not str(data_id).strip():
            raise CleanupOwnershipError("Cleanup target must have a non-empty data id")

    def _db_fallback_cleanup(self, data_item: dict[str, Any]) -> None:
        """DB直连兜底清理（仅限当前测试运行拥有的目标）。"""
        self._validate_owned_target(data_item)
        table_name = self.TABLE_MAP[data_item["type"]]
        if self.db_helper is None:
            raise CleanupOwnershipError(f"DB fallback is disabled for environment {self.env!r}")
        db = self.db_helper.connect()
        try:
            db.execute(
                f"DELETE FROM {table_name} WHERE id = %s AND tenant_id = %s",
                (data_item["id"], data_item["tenant_id"]),
            )
            rowcount = getattr(getattr(db, "cursor", None), "rowcount", None)
            if isinstance(rowcount, int) and rowcount > 1:
                raise RuntimeError(f"DB fallback matched {rowcount} rows; refusing ambiguous cleanup")
            if isinstance(rowcount, int) and rowcount == 0:
                raise RuntimeError("DB fallback matched no owned rows")
            logger.info(f"DB fallback cleanup succeeded for " f"{data_item['type']}:{data_item['id']}")
        finally:
            db.close()

    def _topological_sort(self) -> list[str]:
        """拓扑排序任务依赖（使用Kahn算法，天然支持环检测）

        Kahn算法流程：
        1. 计算每个节点的入度（依赖数量）
        2. 将入度为0的节点加入队列
        3. 依次取出节点，减少其邻居的入度
        4. 如果存在环，剩余节点的入度不会全部变为0

        Returns:
            拓扑排序后的任务名称列表

        Raises:
            ValueError: 检测到循环依赖时抛出
        """
        # 获取所有任务名称
        task_names = [name for name, _, _, _ in self._setup_tasks]

        # 构建邻接表和入度表
        in_degree: dict[str, int] = dict.fromkeys(task_names, 0)
        adjacency: dict[str, list[str]] = {name: [] for name in task_names}

        for node, dependencies in self._dependency_graph.items():
            for dep in dependencies:
                if dep not in adjacency:
                    adjacency[dep] = []
                    in_degree[dep] = 0
                adjacency[dep].append(node)
                in_degree[node] = in_degree.get(node, 0) + 1

        # 将入度为0的节点加入队列
        queue: deque = deque([node for node in task_names if in_degree[node] == 0])

        result: list[str] = []
        while queue:
            node = queue.popleft()
            result.append(node)

            for neighbor in adjacency.get(node, []):
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    queue.append(neighbor)

        # 检测环：如果结果长度小于任务总数，说明存在循环依赖
        if len(result) != len(task_names):
            remaining_nodes = [node for node in task_names if node not in result]
            raise ValueError(
                f"Circular dependency detected in tasks: {remaining_nodes}. "
                f"Dependency graph: {self._dependency_graph}"
            )

        return result

    def _get_cleanup_order(self) -> list[Any]:
        """获取清理顺序（依赖逆序）"""
        # 先清理已创建的数据（按创建时间逆序，后创建的先清理）
        data_order = sorted(
            self._created_data,
            key=lambda x: x["created_at"],
            reverse=True,
        )

        # 再清理注册的清理任务（逆序）
        task_order = list(reversed(self._cleanup_tasks))

        return data_order + task_order

    def _log_cleanup_failure(
        self,
        item: Any,
        api_error: str | None,
        db_error: str | None,
    ) -> None:
        """记录清理失败到日志表"""
        db = None
        try:
            db = self.db_helper.connect()
            db.execute(
                """INSERT INTO cleanup_failure_log
                   (item_type, item_data, api_error, db_error, created_at)
                   VALUES (%s, %s, %s, %s, %s)""",
                (
                    str(type(item).__name__),
                    str(item),
                    api_error,
                    db_error,
                    datetime.now(),
                ),
            )
        except Exception as e:
            logger.error(f"Failed to log cleanup failure: {e}")
        finally:
            if db is not None:
                try:
                    db.close()
                except Exception:
                    logger.exception("Failed to close cleanup failure log connection")

    def _execute_with_retry(self, task: Callable, *args, **kwargs) -> None:
        """带重试机制的任务执行"""
        max_retries = self._retry_config["max_retries"]
        retry_delay = self._retry_config["retry_delay"]

        for attempt in range(max_retries):
            try:
                return task(*args, **kwargs)
            except Exception as e:
                if attempt < max_retries - 1:
                    logger.warning(f"Setup task failed (attempt {attempt + 1}/{max_retries}): {e}")
                    time.sleep(retry_delay)
                else:
                    raise
