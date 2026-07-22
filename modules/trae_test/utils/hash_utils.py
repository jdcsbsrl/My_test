import hashlib


def compute_file_hash(file_path: str) -> str:
    """计算文件的SHA256哈希值

    Args:
        file_path: 文件路径

    Returns:
        文件的SHA256哈希值
    """
    hash_sha256 = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(4096), b""):
            hash_sha256.update(chunk)
    return hash_sha256.hexdigest()


def compute_string_hash(content: str, encoding: str = "utf-8") -> str:
    """计算字符串的SHA256哈希值

    Args:
        content: 字符串内容
        encoding: 编码格式，默认为utf-8

    Returns:
        字符串的SHA256哈希值
    """
    return hashlib.sha256(content.encode(encoding)).hexdigest()


def compute_dict_hash(data: dict) -> str:
    """计算字典的SHA256哈希值（需先序列化）

    Args:
        data: 字典数据

    Returns:
        字典的SHA256哈希值
    """
    import json

    json_str = json.dumps(data, ensure_ascii=False, sort_keys=True)
    return compute_string_hash(json_str)
