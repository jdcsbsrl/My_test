"""Workspace管理工具 - 管理输出文件的目录结构

负责：
- 按北京日期创建workspace子目录
- 生成规范的文件路径
- 管理输出文件位置
"""

from __future__ import annotations

import logging
import threading
from datetime import datetime, timezone, timedelta
from pathlib import Path

logger = logging.getLogger(__name__)


class WorkspaceManager:
    """Workspace管理器"""

    _lock = threading.Lock()
    MAX_PARENT_SEARCH_DEPTH = 10
    FALLBACK_PARENT_LEVEL = 3

    @classmethod
    def _find_project_root(cls, start_path: str) -> str:
        """向上查找项目根目录（通过项目标记文件识别）

        支持的标记文件：AGENTS.md（最高优先级）> .git

        Args:
            start_path: 起始文件路径（通常是 __file__）

        Returns:
            str: 项目根目录的绝对路径
        """
        current = Path(start_path).resolve().parent
        for _ in range(cls.MAX_PARENT_SEARCH_DEPTH):
            if (current / "AGENTS.md").exists() or (current / ".git").exists():
                return str(current)
            current = current.parent
        # fallback: 跳4层（兼容原推导逻辑）
        try:
            return str(Path(start_path).resolve().parents[cls.FALLBACK_PARENT_LEVEL])
        except IndexError:
            return str(Path(start_path).resolve().parent)

    def __init__(self, base_dir: str | None = None):
        """初始化Workspace管理器

        Args:
            base_dir: 基础目录，如果为None则自动推断项目根目录
        """
        if base_dir is None:
            base_dir = self._find_project_root(__file__)
        self.base_dir = Path(base_dir).resolve()
        self.workspace_dir = self.base_dir / "workspace"
        logger.info(f"WorkspaceManager initialized with base_dir={self.base_dir}, workspace_dir={self.workspace_dir}")

    def get_beijing_date(self) -> str:
        """获取北京日期（YYYYMMDD格式）

        Returns:
            str: 北京日期字符串，格式YYYYMMDD
        """
        try:
            from zoneinfo import ZoneInfo

            beijing_tz = ZoneInfo("Asia/Shanghai")
            now = datetime.now(beijing_tz)
        except ImportError:
            now = datetime.now(timezone.utc) + timedelta(hours=8)
        except KeyError as e:
            logger.warning(f"Failed to get Beijing time: {e}, falling back to UTC+8")
            now = datetime.now(timezone.utc) + timedelta(hours=8)

        return now.strftime("%Y%m%d")

    def get_workspace_dir(self) -> Path:
        """获取workspace根目录

        Returns:
            Path: workspace根目录路径
        """
        with self._lock:
            self.workspace_dir.mkdir(parents=True, exist_ok=True)
        logger.debug(f"Ensured workspace directory exists: {self.workspace_dir}")
        return self.workspace_dir

    def get_date_dir(self, date_str: str | None = None) -> Path:
        """获取按日期分类的目录

        Args:
            date_str: 日期字符串（YYYYMMDD），如果为None则使用当前北京日期

        Returns:
            Path: 日期目录路径
        """
        if date_str is None:
            date_str = self.get_beijing_date()

        date_dir = self.workspace_dir / date_str
        with self._lock:
            date_dir.mkdir(parents=True, exist_ok=True)
        logger.debug(f"Ensured date directory exists: {date_dir}")
        return date_dir

    def generate_file_path(
        self,
        requirement_name: str,
        requirement_id: str | None = None,
        date_str: str | None = None,
        sub_dir: str | None = None,
    ) -> Path:
        """生成规范的文件路径

        文件名格式：需求{id}-{需求名}.xlsx
        输出路径：workspace/YYYYMMDD/

        Args:
            requirement_name: 需求名称
            requirement_id: 需求ID（可选）
            date_str: 日期字符串（可选，默认当前北京日期）
            sub_dir: 历史兼容参数，已不再创建 formal/draft 等子目录

        Returns:
            Path: 完整的文件路径

        Raises:
            ValueError: 如果参数无效
        """
        filename = self.generate_filename(requirement_name, requirement_id)
        output_dir = self.get_date_dir(date_str)
        if sub_dir:
            logger.info("Ignoring deprecated workspace sub_dir=%s; writing directly to date directory", sub_dir)
        file_path = output_dir / filename
        logger.debug(f"Generated file path: {file_path}")
        return file_path

    def generate_filename(self, requirement_name: str, requirement_id: str | None = None) -> str:
        """生成规范的文件名

        格式：需求{id}-{需求名}.xlsx
        例如：
        - 需求1001236-销售订单SKU图片显示.xlsx（有需求ID）
        - 需求销售订单导出时间优化.xlsx（无需求ID）

        Args:
            requirement_name: 需求名称
            requirement_id: 需求ID（可选）

        Returns:
            str: 规范的文件名

        Raises:
            ValueError: 如果参数无效
        """
        if not requirement_name or not requirement_name.strip():
            raise ValueError("需求名称不能为空")

        def clean_filename(text: str) -> str:
            for char in ["\\", "/", ":", "*", "?", '"', "<", ">", "|"]:
                text = text.replace(char, "_")
            return " ".join(text.split()).strip()

        req_name = clean_filename(requirement_name)

        if requirement_id and requirement_id.strip():
            req_id = clean_filename(requirement_id)
            filename = f"需求{req_id}-{req_name}.xlsx"
        else:
            filename = f"需求{req_name}.xlsx"

        if len(filename) > 200:
            p = Path(filename)
            stem = p.stem[: 200 - len(p.suffix)]
            filename = f"{stem}{p.suffix}"

        logger.debug(f"Generated filename: {filename}")
        return filename

    def validate_file_path(self, file_path: str) -> tuple[bool, str]:
        """验证文件路径是否符合规范

        Args:
            file_path: 文件路径

        Returns:
            tuple[bool, str]: (是否符合规范, 错误信息)
        """
        p = Path(file_path).resolve()
        if not p.exists():
            return False, f"文件不存在: {file_path}"
        if p.suffix.lower() != ".xlsx":
            return False, f"文件格式必须为.xlsx: {file_path}"

        try:
            relative = p.relative_to(self.workspace_dir)
        except ValueError:
            return False, f"文件必须在workspace目录下: {file_path}"

        parts = relative.parts
        if len(parts) < 2:
            return False, f"文件必须在日期子目录下: {file_path}"

        date_part = parts[0]
        if not (len(date_part) == 8 and date_part.isdigit()):
            return False, f"日期目录格式不正确（应为YYYYMMDD）: {date_part}"

        return self.validate_filename(p.name)

    def validate_filename(self, filename: str) -> tuple[bool, str]:
        """验证文件名是否符合规范

        Args:
            filename: 文件名

        Returns:
            tuple[bool, str]: (是否符合规范, 错误信息)
        """
        if not filename.lower().endswith(".xlsx"):
            return False, f"文件扩展名必须为.xlsx: {filename}"
        if not filename.startswith("需求"):
            return False, f"文件名必须以'需求'开头: {filename}"
        for char in ["\\", "/", ":", "*", "?", '"', "<", ">", "|"]:
            if char in filename:
                return False, f"文件名包含非法字符'{char}': {filename}"
        return True, ""

    def list_date_dirs(self) -> list[str]:
        """列出所有日期目录

        Returns:
            list[str]: 日期目录列表
        """
        workspace_dir = self.get_workspace_dir()
        if not workspace_dir.exists():
            return []

        date_dirs = []
        for item in workspace_dir.iterdir():
            if item.is_dir() and len(item.name) == 8 and item.name.isdigit():
                date_dirs.append(item.name)

        logger.debug(f"Found {len(date_dirs)} date directories")
        return sorted(date_dirs, reverse=True)

    def list_files_in_date_dir(self, date_str: str | None = None) -> list[Path]:
        """列出指定日期目录下的所有文件

        Args:
            date_str: 日期字符串（可选，默认当前北京日期）

        Returns:
            list[Path]: 文件路径列表
        """
        date_dir = self.get_date_dir(date_str)
        if not date_dir.exists():
            return []

        files = []
        for item in date_dir.iterdir():
            if item.is_file() and item.suffix.lower() == ".xlsx":
                files.append(item)

        logger.debug(f"Found {len(files)} files in date directory {date_str}")
        return sorted(files)


workspace_manager = WorkspaceManager()
