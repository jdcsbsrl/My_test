import os
import tempfile

from modules.trae_test.utils.hash_utils import compute_dict_hash, compute_file_hash, compute_string_hash


class TestHashUtils:

    def test_compute_string_hash(self):
        result = compute_string_hash("test_string")
        assert isinstance(result, str)
        assert len(result) == 64
        assert compute_string_hash("test_string") == compute_string_hash("test_string")
        assert compute_string_hash("test_string") != compute_string_hash("different_string")

    def test_compute_string_hash_empty(self):
        result = compute_string_hash("")
        assert isinstance(result, str)
        assert len(result) == 64

    def test_compute_string_hash_unicode(self):
        result = compute_string_hash("测试中文内容")
        assert isinstance(result, str)
        assert len(result) == 64

    def test_compute_file_hash(self):
        with tempfile.NamedTemporaryFile(mode="w", delete=False, encoding="utf-8") as f:
            f.write("test content")
            temp_path = f.name

        try:
            result = compute_file_hash(temp_path)
            assert isinstance(result, str)
            assert len(result) == 64
        finally:
            os.unlink(temp_path)

    def test_compute_file_hash_empty(self):
        with tempfile.NamedTemporaryFile(mode="w", delete=False, encoding="utf-8") as f:
            f.write("")
            temp_path = f.name

        try:
            result = compute_file_hash(temp_path)
            assert isinstance(result, str)
            assert len(result) == 64
        finally:
            os.unlink(temp_path)

    def test_compute_file_hash_binary(self):
        with tempfile.NamedTemporaryFile(mode="wb", delete=False) as f:
            f.write(b"\x00\x01\x02\x03")
            temp_path = f.name

        try:
            result = compute_file_hash(temp_path)
            assert isinstance(result, str)
            assert len(result) == 64
        finally:
            os.unlink(temp_path)

    def test_compute_dict_hash(self):
        data = {"key1": "value1", "key2": 123}
        result = compute_dict_hash(data)
        assert isinstance(result, str)
        assert len(result) == 64

    def test_compute_dict_hash_same_content(self):
        data1 = {"key1": "value1", "key2": 123}
        data2 = {"key2": 123, "key1": "value1"}
        assert compute_dict_hash(data1) == compute_dict_hash(data2)

    def test_compute_dict_hash_different_content(self):
        data1 = {"key1": "value1"}
        data2 = {"key1": "value2"}
        assert compute_dict_hash(data1) != compute_dict_hash(data2)

    def test_compute_dict_hash_empty(self):
        result = compute_dict_hash({})
        assert isinstance(result, str)
        assert len(result) == 64

    def test_compute_dict_hash_nested(self):
        data = {"outer": {"inner": "value"}, "list": [1, 2, 3]}
        result = compute_dict_hash(data)
        assert isinstance(result, str)
        assert len(result) == 64
