import csv
import json
import logging
import os
import random
import re
import string
import tempfile
from collections.abc import Generator
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from faker import Faker
from pydantic import BaseModel, field_validator

from modules.auto_test.core.db_helper import DBHelper

logger = logging.getLogger(__name__)
fake = Faker("zh_CN")


class DataValidationError(Exception):
    pass


class DataLoader:
    """外部数据加载器 - 支持多种文件格式，提供全量加载和流式加载两种模式"""

    def __init__(self, allowed_roots: list[str | os.PathLike[str]] | None = None):
        self._loaders = {
            "json": self._load_json,
            "yaml": self._load_yaml,
            "csv": self._load_csv,
            "xlsx": self._load_excel,
        }
        self._lazy_loaders = {
            "json": self._lazy_load_json,
            "yaml": self._lazy_load_yaml,
            "csv": self._lazy_load_csv,
            "xlsx": self._lazy_load_excel,
        }
        # 检查ijson是否可用，不可用时降级为全量加载
        self._ijson_available = self._check_ijson()
        project_root = Path(__file__).resolve().parents[3]
        roots = allowed_roots or [
            project_root / "data",
            project_root / "fixtures",
            project_root / ".runtime",
            # Existing callers use tempfile-backed fixtures; this remains an isolated
            # test-data root while preventing reads from arbitrary existing files.
            tempfile.gettempdir(),
        ]
        self._allowed_roots = tuple(Path(root).expanduser().resolve() for root in roots)

    def _safe_path(self, file_path: str | os.PathLike[str]) -> Path:
        """Resolve a data path without allowing traversal outside an approved root."""
        try:
            candidate = Path(file_path)
            if not str(candidate).strip():
                raise DataValidationError("Data file path must not be empty")
            resolved = candidate.expanduser().resolve()
        except (TypeError, ValueError, OSError) as exc:
            raise DataValidationError("Invalid data file path") from exc
        if not any(resolved == root or root in resolved.parents for root in self._allowed_roots):
            raise DataValidationError("Data file path is outside the approved data directories")
        if resolved.exists() and not resolved.is_file():
            raise DataValidationError("Data file path must reference a regular file")
        return resolved

    def _check_ijson(self) -> bool:
        """检查ijson库是否可用"""
        try:
            import ijson  # noqa: F401

            return True
        except ImportError:
            logger.warning(
                "ijson library not installed. Lazy loading for JSON will "
                "fallback to full loading. Install with: pip install ijson"
            )
            return False

    def load(self, file_path: str, lazy: bool = False) -> Any:
        """根据文件扩展名自动选择加载器

        Args:
            file_path: 数据文件路径
            lazy: 是否启用懒加载模式（适用于大数据集，避免OOM）

        Returns:
            lazy=True: 返回生成器，按需逐行读取
            lazy=False: 返回完整数据列表（默认）
        """
        safe_path = self._safe_path(file_path)
        ext = safe_path.suffix.lstrip(".").lower()

        if lazy:
            # JSON懒加载需要ijson，如果不可用则降级为全量加载
            if ext == "json" and not self._ijson_available:
                logger.info("ijson not available, falling back to full JSON load")
                return self._load_json(safe_path)

            if ext not in self._lazy_loaders:
                raise DataValidationError(f"Unsupported lazy load format: {ext}")
            return self._lazy_loaders[ext](safe_path)

        if ext not in self._loaders:
            raise DataValidationError(f"Unsupported file format: {ext}")
        return self._loaders[ext](safe_path)

    def _load_json(self, path: str) -> Any:
        with open(path, encoding="utf-8") as f:
            return json.load(f)

    def _lazy_load_json(self, path: str) -> Generator[Any, None, None]:
        """流式加载JSON文件（智能识别根节点类型）

        支持两种JSON格式：
        1. 数组格式: [{...}, {...}]
        2. 对象格式: {"test_cases": [...]} 或 {"data": [...]}

        性能说明：
        - 数组格式：仅 seek(0) 1次
        - 对象格式（含数组字段）：seek(0) 2次
        - 对象格式（数组字段在深层）：可能 seek(0) 2次 + 1次全量回退
        """
        import ijson

        with open(path, encoding="utf-8") as f:
            # 读取第1个非空字符确定根节点类型，避免多余 seek
            head = ""
            while True:
                ch = f.read(1)
                if not ch:  # EOF
                    break
                head = ch
                break
            f.seek(0)

            if head == "[":
                # 根节点是数组 → 仅需 1 次 seek
                for item in ijson.items(f, "item"):
                    yield item
            elif head == "{":
                # 根节点是对象 → 需要 2 次 seek（探测 + 流式读取）
                array_prefix = None
                for prefix, event, value in ijson.parse(f):
                    if event == "start_array":
                        array_prefix = prefix
                        break
                    # 只要发现了第一个 map 的结束即可确认没有数组
                    if event == "end_map" and prefix == "":
                        break

                if array_prefix:
                    f.seek(0)
                    for item in ijson.items(f, f"{array_prefix}.item"):
                        yield item
                else:
                    # 找不到数组字段，回退全量加载
                    f.seek(0)
                    data = json.load(f)
                    for key, value in data.items():
                        if isinstance(value, list):
                            for item in value:
                                yield item
                            return
                    raise DataValidationError("JSON file does not contain an array")
            else:
                raise DataValidationError(f"Unsupported JSON root type: {head[:20]}")

    def _load_yaml(self, path: str) -> Any:
        import yaml

        with open(path, encoding="utf-8") as f:
            return yaml.safe_load(f)

    def _lazy_load_yaml(self, path: str) -> Generator[Any, None, None]:
        """流式加载YAML文件"""
        import yaml

        with open(path, encoding="utf-8") as f:
            for doc in yaml.safe_load_all(f):
                if isinstance(doc, dict):
                    for key, value in doc.items():
                        if isinstance(value, list):
                            for item in value:
                                yield item
                        else:
                            yield value
                elif isinstance(doc, list):
                    for item in doc:
                        yield item

    def _load_csv(self, path: str) -> list[dict[str, Any]]:
        with open(path, encoding="utf-8") as f:
            reader = csv.DictReader(f)
            return list(reader)

    def _lazy_load_csv(self, path: str) -> Generator[dict[str, Any], None, None]:
        """流式加载CSV文件（逐行生成）"""
        with open(path, encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                yield row

    def _load_excel(self, path: str) -> dict[str, Any]:
        import pandas as pd

        df = pd.read_excel(path, sheet_name=None)
        return {sheet: df[sheet].to_dict("records") for sheet in df}

    def _lazy_load_excel(self, path: str, sheet_name: str = 0) -> Generator[dict[str, Any], None, None]:
        """流式加载Excel文件（逐行生成）"""
        import pandas as pd

        for chunk in pd.read_excel(path, sheet_name=sheet_name, chunksize=100):
            for _, row in chunk.iterrows():
                yield row.to_dict()


class DynamicDataGenerator:
    """动态数据生成器 - 支持关联数据和依赖数据"""

    def __init__(self):
        self._generated_cache = {}

    def generate(self, data_type: str, dependencies: dict[str, Any] | None = None, **kwargs) -> Any:
        """生成带依赖关系的数据"""
        if dependencies:
            for key, value in dependencies.items():
                if isinstance(value, str) and value.startswith("$"):
                    dep_key = value[1:]
                    if dep_key not in self._generated_cache:
                        raise DataValidationError(f"Missing dependency: {dep_key}")
                    kwargs[key] = self._generated_cache[dep_key]

        result = self._generate_by_type(data_type, **kwargs)
        if "cache_key" in kwargs:
            self._generated_cache[kwargs["cache_key"]] = result

        return result

    def _generate_by_type(self, data_type: str, **kwargs) -> Any:
        """根据类型生成数据"""
        generators = {
            "random_string": lambda: "".join(random.choices(string.ascii_letters + string.digits, k=10)),
            "random_email": lambda: f"test_{random.randint(1000, 9999)}@example.com",
            "random_phone": lambda: f"1{random.randint(3, 9)}{''.join(random.choices(string.digits, k=9))}",
            "related_order_no": lambda: (
                f"ORD{datetime.now().strftime('%Y%m%d')}"
                f"{''.join(random.choices(string.digits, k=6))}"
            ),
            "random_int": lambda: random.randint(0, 999999),
            "random_float": lambda: round(random.uniform(0, 1000), 2),
            "random_date": lambda: datetime.now().strftime("%Y-%m-%d"),
        }
        return generators.get(data_type, generators["random_string"])()


class DataVersionManager:
    """数据版本管理器"""

    def __init__(self, data_dir: str = "data/test_data"):
        self.data_dir = Path(data_dir).expanduser().resolve()
        self._loader = DataLoader(allowed_roots=[self.data_dir])

    def _ensure_data_dir(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        if self.data_dir.resolve() != self.data_dir or not self.data_dir.is_dir():
            raise DataValidationError("Configured version directory is not a stable directory")

    @staticmethod
    def _validate_identifier(value: str, field_name: str) -> str:
        if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", value):
            raise DataValidationError(f"Invalid {field_name}: path separators and traversal are not allowed")
        return value

    def _version_path(self, data_name: str, version: str) -> Path:
        safe_name = self._validate_identifier(data_name, "data name")
        safe_version = self._validate_identifier(version, "version")
        path = (self.data_dir / f"{safe_name}_v{safe_version}.json").resolve()
        if path.parent != self.data_dir or not (path == self.data_dir / path.name):
            raise DataValidationError("Version path escaped the configured data directory")
        return path

    def _version_files(self, data_name: str) -> list[Path]:
        safe_name = self._validate_identifier(data_name, "data name")
        files = []
        for file_path in self.data_dir.glob(f"{safe_name}_v*.json"):
            resolved = file_path.resolve()
            if resolved.parent != self.data_dir:
                raise DataValidationError("Version file escaped the configured data directory")
            if resolved.is_file():
                files.append(resolved)
        return files

    def get_version(self, data_name: str, version: str = "latest") -> Any:
        """获取指定版本的测试数据"""
        self._validate_identifier(data_name, "data name")
        if version == "latest":
            version = self._get_latest_version(data_name)

        return self._loader.load(self._version_path(data_name, version))

    def _get_latest_version(self, data_name: str) -> str:
        """获取最新版本号"""
        safe_name = self._validate_identifier(data_name, "data name")
        files = self._version_files(safe_name)
        if not files:
            return "1.0"

        versions = [f.name[len(safe_name) + 2 : -len(".json")] for f in files]
        return sorted(versions)[-1]

    def save_version(self, data_name: str, data: Any, version: str) -> None:
        """保存测试数据版本"""
        self._ensure_data_dir()
        file_path = self._version_path(data_name, version)
        with file_path.open("w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def list_versions(self, data_name: str) -> list[str]:
        """列出指定数据的所有版本"""
        safe_name = self._validate_identifier(data_name, "data name")
        files = self._version_files(safe_name)
        versions = []
        for f in files:
            if not f.is_file():
                continue
            version = f.name[len(safe_name) + 2 : -len(".json")]
            versions.append(version)
        return sorted(versions)


class BaseDataGenerator:
    def generate(self, **kwargs) -> Any:
        raise NotImplementedError("Subclasses must implement generate method")

    def validate(self, value: Any) -> bool:
        return True


class StringGenerator(BaseDataGenerator):
    def generate(
        self,
        length: int = 10,
        prefix: str = "",
        suffix: str = "",
        chars: str = string.ascii_letters + string.digits,
        pattern: str | None = None,
    ) -> str:
        if pattern:
            return self._generate_from_pattern(pattern)
        random_str = "".join(random.choices(chars, k=length))
        return f"{prefix}{random_str}{suffix}"

    def _generate_from_pattern(self, pattern: str) -> str:
        result = []
        i = 0
        while i < len(pattern):
            if i + 1 < len(pattern) and pattern[i] == "{":
                end = pattern.find("}", i)
                if end != -1:
                    spec = pattern[i + 1 : end]
                    result.append(self._parse_pattern_spec(spec))
                    i = end + 1
                    continue
            result.append(pattern[i])
            i += 1
        return "".join(result)

    def _parse_pattern_spec(self, spec: str) -> str:
        if spec.startswith("d"):
            length = int(spec[1:]) if len(spec) > 1 else 1
            return "".join(random.choices(string.digits, k=length))
        elif spec.startswith("l"):
            length = int(spec[1:]) if len(spec) > 1 else 1
            return "".join(random.choices(string.ascii_lowercase, k=length))
        elif spec.startswith("u"):
            length = int(spec[1:]) if len(spec) > 1 else 1
            return "".join(random.choices(string.ascii_uppercase, k=length))
        elif spec.startswith("w"):
            length = int(spec[1:]) if len(spec) > 1 else 1
            return "".join(random.choices(string.ascii_letters + string.digits, k=length))
        return ""

    def validate(self, value: Any) -> bool:
        return isinstance(value, str)


class NumericGenerator(BaseDataGenerator):
    def generate(
        self,
        min_value: int = 0,
        max_value: int = 100,
        decimal_places: int = 0,
        step: int = 1,
    ) -> int | float:
        if step <= 0:
            step = 1
        range_size = (max_value - min_value) // step
        value = min_value + random.randint(0, range_size) * step
        if decimal_places > 0:
            return round(value + random.uniform(0, 1), decimal_places)
        return value

    def validate(self, value: Any) -> bool:
        return isinstance(value, (int, float))


class DateTimeGenerator(BaseDataGenerator):
    def generate(
        self,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
        format: str = "%Y-%m-%d %H:%M:%S",
        as_string: bool = True,
    ) -> str | datetime:
        if start_date is None:
            start_date = datetime.now() - timedelta(days=365)
        if end_date is None:
            end_date = datetime.now() + timedelta(days=365)

        delta = end_date - start_date
        random_seconds = random.randint(0, int(delta.total_seconds()))
        result = start_date + timedelta(seconds=random_seconds)

        if as_string:
            return result.strftime(format)
        return result

    def validate(self, value: Any) -> bool:
        return isinstance(value, (datetime, str))


class PersonGenerator(BaseDataGenerator):
    def generate(self, **kwargs) -> dict[str, str]:
        return {
            "name": fake.name(),
            "phone": fake.phone_number(),
            "email": fake.email(),
            "id_card": self._generate_id_card(),
            "address": fake.address(),
        }

    def _generate_id_card(self) -> str:
        region_code = random.choice(["110000", "120000", "310000", "320000", "440000"])
        birth_date = fake.date_of_birth().strftime("%Y%m%d")
        sequence = "".join(random.choices(string.digits, k=3))
        check_code = random.choice(string.digits + ["X"])
        return f"{region_code}{birth_date}{sequence}{check_code}"

    def validate(self, value: Any) -> bool:
        if not isinstance(value, dict):
            return False
        required_fields = ["name", "phone", "email"]
        return all(field in value for field in required_fields)


class AddressGenerator(BaseDataGenerator):
    def generate(self, **kwargs) -> dict[str, str]:
        return {
            "province": fake.province(),
            "city": fake.city(),
            "district": fake.district(),
            "street": fake.street_address(),
            "zipcode": fake.postcode(),
        }

    def validate(self, value: Any) -> bool:
        if not isinstance(value, dict):
            return False
        required_fields = ["province", "city", "street"]
        return all(field in value for field in required_fields)


class ProductGenerator(BaseDataGenerator):
    categories = ["电子产品", "服装鞋帽", "食品饮料", "家居用品", "运动户外"]
    statuses = ["上架", "下架", "审核中"]

    def generate(self, **kwargs) -> dict[str, Any]:
        return {
            "sku_code": self._generate_sku_code(),
            "name": fake.word() + "产品",
            "english_name": fake.word().capitalize(),
            "category": random.choice(self.categories),
            "status": random.choice(self.statuses),
            "price": round(random.uniform(10, 1000), 2),
            "stock": random.randint(0, 1000),
        }

    def _generate_sku_code(self) -> str:
        prefix = random.choice(["SKU", "PRD", "ITEM"])
        num_part = "".join(random.choices(string.digits, k=6))
        return f"{prefix}{num_part}"

    def validate(self, value: Any) -> bool:
        if not isinstance(value, dict):
            return False
        required_fields = ["sku_code", "name", "category", "status"]
        return all(field in value for field in required_fields)


class OrderGenerator(BaseDataGenerator):
    def generate(self, **kwargs) -> dict[str, Any]:
        return {
            "order_no": self._generate_order_no(),
            "customer_name": fake.name(),
            "customer_phone": fake.phone_number(),
            "total_amount": round(random.uniform(100, 10000), 2),
            "status": random.choice(["待付款", "已付款", "待发货", "已发货", "已完成"]),
            "create_time": fake.date_time_this_month().strftime("%Y-%m-%d %H:%M:%S"),
            "items": self._generate_order_items(random.randint(1, 5)),
        }

    def _generate_order_no(self) -> str:
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        suffix = "".join(random.choices(string.digits, k=4))
        return f"ORD{timestamp}{suffix}"

    def _generate_order_items(self, count: int) -> list[dict[str, Any]]:
        product_gen = ProductGenerator()
        items = []
        for _ in range(count):
            product = product_gen.generate()
            items.append(
                {
                    "sku_code": product["sku_code"],
                    "name": product["name"],
                    "quantity": random.randint(1, 10),
                    "price": product["price"],
                }
            )
        return items

    def validate(self, value: Any) -> bool:
        if not isinstance(value, dict):
            return False
        required_fields = ["order_no", "customer_name", "total_amount", "status"]
        return all(field in value for field in required_fields)


class SalesOrderItemGenerator(BaseDataGenerator):
    product_categories = [
        ("DME", "男装"),
        ("DWO", "女装"),
        ("DUN", "内衣"),
        ("DSH", "鞋子"),
        ("DJE", "饰品"),
        ("DBA", "箱包"),
        ("DCM", "亲子母婴"),
        ("DPC", "个护清洁"),
        ("DHO", "居家生活"),
        ("DEC", "电子3C"),
        ("DPE", "宠物"),
        ("DPK", "包材"),
        ("DSU", "食品"),
    ]

    def generate(self, **kwargs) -> dict[str, Any]:
        order_no = kwargs.get("order_no", self._generate_order_no())
        item_id = self._generate_item_id()
        sku_code = self._generate_sku_code()

        return {
            "id": random.randint(100000, 999999),
            "order_no": order_no,
            "order_id": self._generate_platform_order_no(),
            "item_id": item_id,
            "seller_sku": sku_code,
            "quantity": random.randint(1, 100),
            "item_unit_price": round(random.uniform(10, 1000), 2),
            "customization": fake.text(max_nb_chars=100) if random.random() > 0.7 else None,
            "sku_img": f"https://example.com/images/{sku_code}.jpg",
            "order_item_no": f"{order_no}-{random.randint(1, 999)}",
            "create_by": random.randint(1, 100),
            "create_time": fake.date_time_this_month().strftime("%Y-%m-%d %H:%M:%S"),
            "update_by": random.randint(1, 100) if random.random() > 0.5 else None,
            "update_time": fake.date_time_this_month().strftime("%Y-%m-%d %H:%M:%S") if random.random() > 0.5 else None,
            "create_dept": random.randint(1, 10),
            "tenant_id": "000000",
            "purchase_status": str(random.randint(0, 2)),
            "sku_coefficient_qty": random.randint(0, 10),
            "merge_order_no": None,
            "sku_color_size": self._generate_color_size(),
            "sku_weight": round(random.uniform(10, 1000), 3),
            "cost": round(random.uniform(5, 500), 2),
            "store_id": random.randint(1, 10),
            "seller_id": str(random.randint(1000, 9999)),
            "marketplace_id": str(random.randint(1, 10)),
            "sku_mapping_status": random.choice(["Y", "N"]),
            "sales_man": fake.name(),
            "location_id": random.randint(1, 50),
            "so_id": random.randint(1000, 9999),
            "group_sku_id": None,
            "product_id": str(random.randint(1000, 9999)),
            "price": round(random.uniform(10, 1000), 2),
            "bg_chinesename": fake.word() + "商品",
            "bg_englishname": fake.word().capitalize(),
            "bg_quantity": random.randint(1, 100),
            "bg_item_unit_price": round(random.uniform(1, 100), 2),
            "bg_sku_weight": round(random.uniform(10, 1000), 3),
            "bg_hs_code": "".join(random.choices(string.digits, k=8)),
            "lock_stock_qty": random.randint(0, 50),
            "remark": fake.text(max_nb_chars=50) if random.random() > 0.7 else None,
            "purchase_remark": None,
            "variant_id": str(random.randint(1000, 9999)),
            "title": fake.sentence(nb_words=3),
            "fulfillment_line_items_id": None,
            "quantity_replenishment": random.randint(0, 100),
            "deficit_flag": random.randint(0, 1),
            "receivable_price": round(random.uniform(10, 1000), 2),
            "receivable_currency": "CNY",
            "handle": fake.word(),
            "fulfillment_id": None,
            "group_sku_qty": None,
            "shopify_line_item_id": None,
            "shopify_product_title": None,
            "receivable_total_amount": round(random.uniform(10, 10000), 2),
            "quotation_discount_amount": round(random.uniform(0, 100), 2),
            "pod_properties": None,
            "pod_properties1": None,
            "pod_properties2": None,
            "pod_properties3": None,
            "pod_properties4": None,
            "pod_properties5": None,
            "pod_properties6": None,
            "pod_properties7": None,
            "pod_properties8": None,
            "pod_properties9": None,
            "pod_properties10": None,
            "platform_quantity": random.randint(1, 100),
            "receivable_error": None,
            "preview_type": None,
            "preview_id": None,
        }

    def _generate_order_no(self) -> str:
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        suffix = "".join(random.choices(string.digits, k=4))
        return f"ORD{timestamp}{suffix}"

    def _generate_platform_order_no(self) -> str:
        return f"PO{random.randint(1000000000, 9999999999)}"

    def _generate_item_id(self) -> str:
        return f"ITEM{random.randint(100000, 999999)}"

    def _generate_sku_code(self) -> str:
        category_code = random.choice(self.product_categories)[0]
        return f"{category_code}{random.randint(1000, 9999)}"

    def _generate_color_size(self) -> str:
        colors = ["黑色", "白色", "红色", "蓝色", "灰色", "黄色"]
        sizes = ["S", "M", "L", "XL", "XXL", "均码"]
        return f"{random.choice(colors)}/{random.choice(sizes)}"

    def validate(self, value: Any) -> bool:
        if not isinstance(value, dict):
            return False
        required_fields = ["id", "order_no", "item_id", "seller_sku", "quantity", "item_unit_price"]
        return all(field in value for field in required_fields)


class TestDataFactory:
    """测试数据工厂 - 使用实例变量而非类变量，避免子类共享状态污染"""

    def __init__(self):
        # 使用实例变量避免 EnhancedTestDataFactory 等子类共享同一字典
        self._generators: dict[str, BaseDataGenerator] = {}
        self._register_generators()

    def _register_generators(self) -> None:
        self._generators["string"] = StringGenerator()
        self._generators["numeric"] = NumericGenerator()
        self._generators["datetime"] = DateTimeGenerator()
        self._generators["person"] = PersonGenerator()
        self._generators["address"] = AddressGenerator()
        self._generators["product"] = ProductGenerator()
        self._generators["order"] = OrderGenerator()
        self._generators["sales_order_item"] = SalesOrderItemGenerator()

    def generate(
        self,
        data_type: str,
        count: int = 1,
        validate: bool = True,
        **kwargs,
    ) -> Any | list[Any]:
        if data_type not in self._generators:
            raise DataValidationError(f"Unsupported data type: {data_type}")

        generator = self._generators[data_type]

        if count == 1:
            result = generator.generate(**kwargs)
            if validate and not generator.validate(result):
                raise DataValidationError(f"Generated data validation failed for {data_type}")
            return result

        results = []
        for _ in range(count):
            result = generator.generate(**kwargs)
            if validate and not generator.validate(result):
                raise DataValidationError(f"Generated data validation failed for {data_type}")
            results.append(result)
        return results

    def register_generator(self, name: str, generator: BaseDataGenerator) -> None:
        self._generators[name] = generator

    def get_generator(self, name: str) -> BaseDataGenerator | None:
        return self._generators.get(name)

    def generate_from_schema(self, schema: dict[str, Any]) -> dict[str, Any]:
        result = {}
        for field_name, field_spec in schema.items():
            data_type = field_spec.get("type", "string")
            options = field_spec.get("options", {})

            if field_spec.get("required", False) and "default" not in field_spec:
                result[field_name] = self.generate(data_type, **options)
            elif "default" in field_spec:
                result[field_name] = field_spec["default"]
            elif field_spec.get("nullable", False):
                result[field_name] = None if random.random() < 0.1 else self.generate(data_type, **options)

        return result


class DataSchema(BaseModel):
    name: str
    fields: dict[str, dict[str, Any]]

    @field_validator("fields")
    def validate_fields(cls, v):
        for field_name, spec in v.items():
            if "type" not in spec:
                raise ValueError(f"Field '{field_name}' must have a 'type'")
        return v


class SchemaBasedFactory:
    def __init__(self):
        self.factory = TestDataFactory()

    def generate_from_schema(self, schema: dict | DataSchema) -> dict[str, Any]:
        if isinstance(schema, dict):
            schema = DataSchema(**schema)

        return self.factory.generate_from_schema(schema.fields)

    def generate_many_from_schema(self, schema: dict | DataSchema, count: int) -> list[dict[str, Any]]:
        results = []
        for _ in range(count):
            results.append(self.generate_from_schema(schema))
        return results


class DatabaseDataGenerator(BaseDataGenerator):
    """数据库数据生成器 - 支持从数据库获取测试数据（含SQL注入防护）"""

    # 白名单表名
    ALLOWED_TABLES = {
        "oms_inventory",
        "sales_order",
        "sales_order_item",
        "oms_sku",
        "oms_product",
        "oms_warehouse",
    }

    def __init__(self):
        self.db_helper = None

    def _ensure_connection(self):
        if not self.db_helper or not getattr(self.db_helper, "connection", None) or not getattr(
            self.db_helper, "cursor", None
        ):
            self.db_helper = DBHelper().connect()
        return self.db_helper

    def _validate_table_name(self, table_name: str) -> None:
        """表名白名单校验"""
        if table_name not in self.ALLOWED_TABLES:
            raise DataValidationError(
                f"Unauthorized table access: {table_name}. " f"Allowed tables: {self.ALLOWED_TABLES}"
            )

    def _validate_column_name(self, column: str) -> None:
        """字段名校验（仅允许字母数字下划线）"""
        if not re.match(r"^[a-zA-Z_][a-zA-Z0-9_]*$", column):
            raise DataValidationError(f"Invalid column name: {column}")

    def generate(
        self,
        table_name: str,
        columns: list[str] | None = None,
        filters: dict[str, Any] | None = None,
        limit: int = 1,
        random_sample: bool = False,
        **kwargs,
    ) -> dict[str, Any] | list[dict[str, Any]]:
        # 表名白名单校验
        self._validate_table_name(table_name)

        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 10000:
            raise DataValidationError("Query limit must be an integer between 1 and 10000")

        if columns:
            # 字段名校验
            for col in columns:
                self._validate_column_name(col)
            col_str = ", ".join(columns)
        else:
            col_str = "*"

        # 安全的查询构建
        db = self._ensure_connection()
        query = f"SELECT {col_str} FROM {table_name}"

        params = []
        if filters:
            where_clauses = []
            for key, value in filters.items():
                self._validate_column_name(key)
                if value is None:
                    where_clauses.append(f"{key} IS NULL")
                else:
                    where_clauses.append(f"{key} = %s")
                    params.append(value)

            if where_clauses:
                query += " WHERE " + " AND ".join(where_clauses)

        if random_sample:
            query += " ORDER BY RANDOM()"

        query += " LIMIT %s"
        params.append(limit)

        try:
            result = db.execute(query, tuple(params))

            if limit == 1:
                return result[0] if result else {}
            return result
        finally:
            if "close_connection" in kwargs and kwargs["close_connection"]:
                db.close()

    def get_random_inventory(self) -> dict[str, Any]:
        return self.generate(
            table_name="oms_inventory",
            columns=["id", "item_id", "display_name", "english_name", "sku_weight", "status"],
            random_sample=True,
            limit=1,
        )

    def get_random_sales_order(self) -> dict[str, Any]:
        return self.generate(
            table_name="sales_order",
            columns=["id", "order_no", "platform", "order_status", "total_amount", "create_time"],
            random_sample=True,
            limit=1,
        )

    def get_order_items(self, order_no: str) -> list[dict[str, Any]]:
        return self.generate(
            table_name="sales_order_item",
            filters={"order_no": order_no},
            limit=100,
        )

    def get_inventory_by_item_id(self, item_id: str) -> dict[str, Any] | None:
        result = self.generate(
            table_name="oms_inventory",
            filters={"item_id": item_id},
            limit=1,
        )
        return result if isinstance(result, dict) else None

    def validate(self, value: Any) -> bool:
        return isinstance(value, (dict, list))


class EnhancedTestDataFactory(TestDataFactory):
    def __init__(self):
        super().__init__()
        self._register_generators()

    def _register_generators(self) -> None:
        super()._register_generators()
        self._generators["database"] = DatabaseDataGenerator()

    def get_random_inventory(self) -> dict[str, Any]:
        generator = self._generators["database"]
        return generator.get_random_inventory()

    def get_random_sales_order(self) -> dict[str, Any]:
        generator = self._generators["database"]
        return generator.get_random_sales_order()

    def get_order_items(self, order_no: str) -> list[dict[str, Any]]:
        generator = self._generators["database"]
        return generator.get_order_items(order_no)

    def get_inventory_by_item_id(self, item_id: str) -> dict[str, Any] | None:
        generator = self._generators["database"]
        return generator.get_inventory_by_item_id(item_id)


def get_test_data_factory() -> TestDataFactory:
    return TestDataFactory()


def get_schema_factory() -> SchemaBasedFactory:
    return SchemaBasedFactory()


def get_enhanced_test_data_factory() -> EnhancedTestDataFactory:
    return EnhancedTestDataFactory()
