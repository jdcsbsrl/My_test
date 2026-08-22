"""单元测试：test_data_factory.py 扩展功能

测试范围：
- DataLoader（多格式加载器 + 流式/懒加载）
- DynamicDataGenerator（动态数据生成）
- DataVersionManager（数据版本控制）
- DatabaseDataGenerator SQL注入防护
- TestDataFactory _generators 实例变量修复
"""

import json
import os
import tempfile

import pytest

from modules.auto_test.core.test_data_factory import (
    DatabaseDataGenerator,
    DataLoader,
    DataValidationError,
    DataVersionManager,
    DynamicDataGenerator,
    EnhancedTestDataFactory,
    TestDataFactory as FactoryUnderTest,
)


class TestDataLoader:
    """测试DataLoader类"""

    def setup_method(self):
        self.loader = DataLoader()
        self.temp_dir = tempfile.mkdtemp()

    def _create_temp_file(self, content: str, suffix: str) -> str:
        """创建临时文件并返回路径"""
        fd, path = tempfile.mkstemp(suffix=suffix, dir=self.temp_dir)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(content)
        return path

    # ── JSON 加载测试 ──────────────────────────────────────

    def test_load_json_object(self):
        """测试加载JSON对象格式"""
        data = {"test_cases": [{"id": 1, "name": "test1"}, {"id": 2, "name": "test2"}]}
        path = self._create_temp_file(json.dumps(data, ensure_ascii=False), ".json")
        result = self.loader.load(path)
        assert result["test_cases"][0]["id"] == 1
        assert len(result["test_cases"]) == 2

    def test_load_json_array(self):
        """测试加载JSON数组格式"""
        data = [{"id": 1}, {"id": 2}]
        path = self._create_temp_file(json.dumps(data), ".json")
        result = self.loader.load(path)
        assert len(result) == 2
        assert result[0]["id"] == 1

    def test_load_json_invalid_file(self):
        """测试加载无效JSON文件"""
        path = self._create_temp_file("invalid json content", ".json")
        with pytest.raises(json.JSONDecodeError):
            self.loader.load(path)

    def test_load_json_file_not_found(self):
        """测试加载不存在的JSON文件"""
        with pytest.raises(FileNotFoundError):
            self.loader.load(os.path.join(tempfile.gettempdir(), "nonexistent", "file.json"))

    # ── CSV 加载测试 ───────────────────────────────────────

    def test_load_csv(self):
        """测试加载CSV文件"""
        content = "id,name,age\n1,Alice,30\n2,Bob,25\n"
        path = self._create_temp_file(content, ".csv")
        result = self.loader.load(path)
        assert len(result) == 2
        assert result[0]["name"] == "Alice"
        assert result[1]["age"] == "25"

    def test_load_csv_empty(self):
        """测试加载空CSV文件"""
        content = "id,name,age\n"
        path = self._create_temp_file(content, ".csv")
        result = self.loader.load(path)
        assert result == []

    # ── YAML 加载测试 ──────────────────────────────────────

    def test_load_yaml(self):
        """测试加载YAML文件"""
        content = "name: test\nvalue: 123\nitems:\n  - a\n  - b\n"
        path = self._create_temp_file(content, ".yaml")
        result = self.loader.load(path)
        assert result["name"] == "test"
        assert result["value"] == 123
        assert result["items"] == ["a", "b"]

    # ── 流式加载测试 ───────────────────────────────────────

    def test_lazy_load_csv(self):
        """测试CSV流式加载"""
        content = "id,name\n" + "\n".join(f"{i},name_{i}" for i in range(100))
        path = self._create_temp_file(content, ".csv")
        result = self.loader.load(path, lazy=True)

        # 验证返回的是生成器
        import types

        assert isinstance(result, types.GeneratorType)

        # 验证数据正确
        items = list(result)
        assert len(items) == 100
        assert items[0]["id"] == "0"

    # ── 格式不支持测试 ─────────────────────────────────────

    def test_unsupported_format(self):
        """测试不支持的格式"""
        with pytest.raises(DataValidationError, match="Unsupported file format"):
            self.loader.load(os.path.join(self.temp_dir, "test.unsupported"))

    def test_unsupported_lazy_format(self):
        """测试不支持的懒加载格式"""
        with pytest.raises(DataValidationError, match="Unsupported lazy load format"):
            self.loader.load(os.path.join(self.temp_dir, "test.unsupported"), lazy=True)


class TestDynamicDataGenerator:
    """测试DynamicDataGenerator类"""

    def setup_method(self):
        self.generator = DynamicDataGenerator()

    def test_generate_random_string(self):
        """测试生成随机字符串"""
        result = self.generator.generate("random_string")
        assert isinstance(result, str)
        assert len(result) == 10

    def test_generate_random_email(self):
        """测试生成随机邮箱"""
        result = self.generator.generate("random_email")
        assert isinstance(result, str)
        assert "@" in result

    def test_generate_random_phone(self):
        """测试生成随机手机号"""
        result = self.generator.generate("random_phone")
        assert isinstance(result, str)
        assert result.startswith("1")
        assert len(result) == 11

    def test_generate_related_order_no(self):
        """测试生成关联订单号"""
        result = self.generator.generate("related_order_no")
        assert isinstance(result, str)
        assert result.startswith("ORD")

    def test_generate_with_cache(self):
        """测试缓存功能"""
        result1 = self.generator.generate("random_string", cache_key="my_key")
        result2 = self.generator.generate("random_string", cache_key="my_key")
        assert result1 != result2  # 每次生成不同值

    def test_generate_with_dependency(self):
        """测试依赖数据生成"""
        # 先生成并缓存订单号
        order_no = self.generator.generate("related_order_no", cache_key="order")

        # 使用缓存的订单号作为依赖
        result = self.generator.generate("random_string", dependencies={"order_no": "$order"})
        assert isinstance(result, str)

    def test_generate_missing_dependency(self):
        """测试缺少依赖"""
        with pytest.raises(DataValidationError, match="Missing dependency"):
            self.generator.generate("random_string", dependencies={"order_no": "$nonexistent_key"})

    def test_generate_random_int(self):
        """测试生成随机整数"""
        result = self.generator.generate("random_int")
        assert isinstance(result, int)
        assert 0 <= result <= 999999

    def test_generate_random_float(self):
        """测试生成随机浮点数"""
        result = self.generator.generate("random_float")
        assert isinstance(result, float)
        assert 0 <= result <= 1000

    def test_generate_random_date(self):
        """测试生成随机日期"""
        result = self.generator.generate("random_date")
        assert isinstance(result, str)
        assert len(result) == 10  # YYYY-MM-DD


class TestDataVersionManager:
    """测试DataVersionManager类"""

    def setup_method(self):
        self.temp_dir = tempfile.mkdtemp()
        self.manager = DataVersionManager(data_dir=self.temp_dir)

    def test_save_and_get_version(self):
        """测试保存和获取指定版本"""
        data = {"name": "test", "value": 123}
        self.manager.save_version("test_data", data, "1.0")

        result = self.manager.get_version("test_data", version="1.0")
        assert result["name"] == "test"
        assert result["value"] == 123

    def test_get_latest_version(self):
        """测试获取最新版本"""
        self.manager.save_version("test_data", {"v": 1}, "1.0")
        self.manager.save_version("test_data", {"v": 2}, "2.0")

        result = self.manager.get_version("test_data")  # latest
        assert result["v"] == 2

    def test_get_latest_version_no_files(self):
        """测试获取最新版本（无文件时返回1.0）"""
        version = self.manager._get_latest_version("nonexistent")
        assert version == "1.0"

    def test_list_versions(self):
        """测试列出所有版本"""
        self.manager.save_version("test_data", {"v": 1}, "1.0")
        self.manager.save_version("test_data", {"v": 2}, "2.0")

        versions = self.manager.list_versions("test_data")
        assert versions == ["1.0", "2.0"]

    def test_save_version_creates_directory(self):
        """测试保存版本时自动创建目录"""
        nested_dir = os.path.join(self.temp_dir, "nested", "dir")
        manager = DataVersionManager(data_dir=nested_dir)
        manager.save_version("test_data", {"v": 1}, "1.0")

        assert os.path.exists(nested_dir)
        assert os.path.exists(os.path.join(nested_dir, "test_data_v1.0.json"))


class TestDatabaseDataGeneratorSecurity:
    """测试DatabaseDataGenerator SQL注入防护"""

    def setup_method(self):
        self.generator = DatabaseDataGenerator()

    def test_invalid_table_name(self):
        """测试非法表名被拒绝"""
        with pytest.raises(DataValidationError, match="Unauthorized table access"):
            self.generator._validate_table_name("users; DROP TABLE users; --")

    def test_invalid_column_name(self):
        """测试非法字段名被拒绝"""
        with pytest.raises(DataValidationError, match="Invalid column name"):
            self.generator._validate_column_name("name; DROP TABLE users; --")

    def test_invalid_filter_key(self):
        """测试非法过滤条件被拒绝"""
        with pytest.raises(DataValidationError, match="Invalid column name"):
            self.generator._validate_column_name("id; DROP TABLE users; --")

    def test_valid_table_allowed(self):
        """测试合法表名通过校验"""
        # 由于没有真实数据库连接，会抛出连接错误而不是数据校验错误
        # 验证表名校验通过
        self.generator._validate_table_name("oms_inventory")
        self.generator._validate_table_name("sales_order")
        self.generator._validate_table_name("sales_order_item")

    def test_valid_column_name(self):
        """测试合法字段名通过校验"""
        # 验证字段名校验通过
        self.generator._validate_column_name("id")
        self.generator._validate_column_name("order_no")
        self.generator._validate_column_name("display_name")


class TestTestDataFactoryGenerators:
    """测试TestDataFactory _generators实例变量修复"""

    def test_generators_are_instance_variables(self):
        """测试_generators是实例变量而非类变量"""
        factory1 = FactoryUnderTest()
        factory2 = FactoryUnderTest()

        # 修改factory1的generators不应影响factory2
        factory1._generators["custom"] = None
        assert "custom" not in factory2._generators

    def test_enhanced_factory_independent_generators(self):
        """测试EnhancedTestDataFactory拥有独立的_generators"""
        factory = FactoryUnderTest()
        enhanced = EnhancedTestDataFactory()

        # 增强工厂有database生成器，普通工厂没有
        assert "database" in enhanced._generators
        assert "database" not in factory._generators

    def test_register_generator_independence(self):
        """测试注册自定义生成器不会互相影响"""
        factory1 = FactoryUnderTest()
        factory2 = FactoryUnderTest()

        from modules.auto_test.core.test_data_factory import StringGenerator

        factory1.register_generator("my_custom_string", StringGenerator())

        assert "my_custom_string" in factory1._generators
        assert "my_custom_string" not in factory2._generators
