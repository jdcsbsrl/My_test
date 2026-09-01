import os
import re
from pathlib import Path

CHUNK_FILENAME_PATTERN = re.compile(r".+_chunk_\d+\.json$")


def is_chunk_filename(filename: str) -> bool:
    """判断文件名是否符合知识库分块文件的命名规范

    格式: <file_title>_chunk_<N>.json 或 <file_title>_KEY_chunk_<N>.json

    Args:
        filename: 待检查的文件名

    Returns:
        是否为合法的分块文件名
    """
    return bool(CHUNK_FILENAME_PATTERN.match(filename))


def find_project_root(start_file: str) -> str:
    """通过项目标记文件向上搜索定位项目根目录

    支持的标记文件：AGENTS.md（最高优先级）> .git

    Args:
        start_file: 起始文件路径（通常是 __file__）

    Returns:
        项目根目录的绝对路径
    """
    current = Path(start_file).resolve().parent
    for _ in range(10):
        if (current / "AGENTS.md").exists() or (current / ".git").exists():
            return str(current)
        current = current.parent
    return str(Path(start_file).resolve().parent)


class PathManager:
    """统一路径管理工具类"""

    _kb_base_dir = None

    @classmethod
    def get_kb_base_dir(cls) -> str:
        """获取知识库基础目录"""
        if cls._kb_base_dir is None:
            project_root = find_project_root(__file__)
            cls._kb_base_dir = os.path.normpath(os.path.join(project_root, "assets", "knowledge_base"))
        return cls._kb_base_dir

    @classmethod
    def get_data_dir(cls) -> str:
        """获取数据目录"""
        return os.path.join(cls.get_kb_base_dir(), "data")

    @classmethod
    def get_original_dir(cls) -> str:
        """获取原始文件目录"""
        return os.path.join(cls.get_data_dir(), "original")

    @classmethod
    def get_chunks_dir(cls) -> str:
        """获取分块文件目录"""
        return os.path.join(cls.get_data_dir(), "chunks")

    @classmethod
    def get_index_dir(cls) -> str:
        """获取索引目录"""
        return os.path.join(cls.get_kb_base_dir(), "index")

    @classmethod
    def get_metadata_dir(cls) -> str:
        """获取元数据目录"""
        return os.path.join(cls.get_kb_base_dir(), "metadata")

    @classmethod
    def ensure_directories(cls, *dirs: str) -> None:
        """确保指定目录存在"""
        for dir_path in dirs:
            if not os.path.exists(dir_path):
                os.makedirs(dir_path, exist_ok=True)

    @classmethod
    def ensure_kb_directories(cls) -> None:
        """确保知识库所有必要目录存在"""
        cls.ensure_directories(
            cls.get_kb_base_dir(),
            cls.get_data_dir(),
            cls.get_original_dir(),
            cls.get_chunks_dir(),
            cls.get_index_dir(),
            cls.get_metadata_dir(),
        )
