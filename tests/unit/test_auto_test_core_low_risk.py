import json
import time
from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest
import requests
import yaml

from modules.auto_test.core import agent_progress, environment, execution_auth
from modules.auto_test.core.auth_engine import AuthEngine
from modules.auto_test.core.login_service import LoginService
from modules.auto_test.core.secret_manager import SecretManager, _origin_from_api_base
from modules.auto_test.core.token_manager import TokenInfo, TokenManager


pytestmark = pytest.mark.unit


def reset_singletons() -> None:
    environment.Environment.reset()
    execution_auth.ExecutionAuthManager._instance = None
    SecretManager._instance = None
    TokenManager._instance = None
    LoginService._instance = None


class TestAgentProgress:
    def test_load_progress_json_returns_empty_when_file_missing(self, tmp_path):
        assert agent_progress.load_progress_json(tmp_path) == {}

    def test_validate_progress_reports_schema_status_phase_and_duplicates(self):
        data = {
            "schema_version": 0,
            "features": [
                {"id": "sku", "status": "unknown", "phase": "bad"},
                {"id": "sku", "status": "done", "phase": "coding"},
            ],
            "events": "not-a-list",
        }

        errors = agent_progress.validate_progress(data)

        assert "schema_version must be >= 1" in errors
        assert "features[0].status invalid: unknown" in errors
        assert "features[0].phase invalid: bad" in errors
        assert "duplicate feature id: sku" in errors
        assert "'events' must be a list when present" in errors

    def test_progress_summary_counts_only_dict_features(self):
        summary = agent_progress.progress_summary(
            {"features": [{"status": "done"}, {"status": "done"}, {"id": "x"}, "bad"]}
        )

        assert summary == {"feature_count": 4, "by_status": {"done": 2, "planned": 1}}


class TestEnvironment:
    def setup_method(self):
        reset_singletons()

    def teardown_method(self):
        reset_singletons()

    def test_environment_type_blocks_production(self):
        assert environment.EnvironmentType.is_allowed("uat")
        assert not environment.EnvironmentType.is_allowed("production")
        with pytest.raises(environment.EnvironmentSecurityError):
            environment.validate_environment("production")

    def test_resolve_env_vars_supports_defaults_and_nested_values(self, monkeypatch):
        monkeypatch.setenv("ERP_HOST", "https://example.test")
        env = object.__new__(environment.Environment)

        resolved = env._resolve_env_vars(
            {"origin": "${ERP_HOST}", "missing": "${MISSING:-fallback}", "items": ["${MISSING:-x}", 3]}
        )

        assert resolved == {"origin": "https://example.test", "missing": "fallback", "items": ["x", 3]}

    def test_load_endpoints_builds_urls_from_config(self):
        env = object.__new__(environment.Environment)
        env._config = {"origin": "https://erp.test", "ui_path": "/oms-ui", "api_path": "/api"}

        env._load_endpoints("test")

        assert env.endpoints.base_url == "https://erp.test/oms-ui"
        assert env.endpoints.api_base_url == "https://erp.test/api"
        assert env.endpoints.auth_url == "https://erp.test/api/oms-admin/auth/login"

    def test_get_set_and_config_property_returns_deep_copy(self):
        env = object.__new__(environment.Environment)
        env._config = {"api": {"timeout": 5}}
        env._env_name = "test"

        env.set("playwright.viewport.width", 1366)
        cfg = env.config
        cfg["api"]["timeout"] = 10

        assert env.get("playwright.viewport.width") == 1366
        assert env.get("missing.key", "default") == "default"
        assert env.get("api.timeout") == 5
        assert env.name == "test"
        assert env.is_test
        assert not env.is_uat


class TestSecretManager:
    def setup_method(self):
        reset_singletons()

    def teardown_method(self):
        reset_singletons()

    def test_origin_from_api_base_uses_scheme_and_host_only(self):
        assert _origin_from_api_base("https://erp.test/api/v1") == "https://erp.test"

    def test_get_credentials_caches_environment_values(self, monkeypatch):
        monkeypatch.setenv("TEST_USERNAME", "alice")
        monkeypatch.setenv("TEST_PASSWORD", "secret")
        manager = SecretManager()

        first = manager.get_credentials()
        monkeypatch.setenv("TEST_USERNAME", "bob")
        second = manager.get_credentials()

        assert first.username == "alice"
        assert second is first

    def test_get_credentials_raises_when_missing(self, monkeypatch):
        monkeypatch.delenv("TEST_USERNAME", raising=False)
        monkeypatch.delenv("TEST_PASSWORD", raising=False)

        with pytest.raises(ValueError, match="Credentials not found"):
            SecretManager().get_credentials()

    def test_get_auth_config_uses_env_specific_values_and_origin_fallback(self, monkeypatch):
        monkeypatch.setenv("TEST_UAT_CLIENTID", "client-uat")
        monkeypatch.setenv("TEST_UAT_ENCRYPT_KEY", "encrypt-uat")
        monkeypatch.delenv("TEST_UAT_ORIGIN", raising=False)
        manager = SecretManager()

        config = manager.get_auth_config(api_base_url="https://uat.erp.test/oms-api", env="uat")

        assert config.clientid == "client-uat"
        assert config.encrypt_key == "encrypt-uat"
        assert config.isencrypt == "true"
        assert config.content_language == "zh_CN"
        assert config.origin == "https://uat.erp.test"

    def test_get_api_login_password_payload_prefers_encrypted_password(self, monkeypatch):
        monkeypatch.setenv("TEST_ENCRYPTED_LOGIN_PASSWORD", "encrypted")
        monkeypatch.setenv("TEST_PASSWORD", "plain")

        assert SecretManager().get_api_login_password_payload() == "encrypted"

    def test_reset_clears_cache_and_releases_singleton(self, monkeypatch):
        monkeypatch.setenv("TEST_USERNAME", "alice")
        monkeypatch.setenv("TEST_PASSWORD", "secret")
        manager = SecretManager()
        manager.get_credentials()

        SecretManager.reset()
        fresh = SecretManager()

        assert fresh is not manager
        assert fresh._secrets_cache == {}

    def test_clear_cache_removes_cached_credentials_config_password_and_proxy(self, monkeypatch):
        monkeypatch.setenv("TEST_USERNAME", "alice")
        monkeypatch.setenv("TEST_PASSWORD", "secret")
        monkeypatch.setenv("TEST_CLIENTID", "client-1")
        monkeypatch.setenv("TEST_ENCRYPT_KEY", "key-1")
        monkeypatch.setenv("TEST_ENCRYPTED_LOGIN_PASSWORD", "encrypted-1")
        monkeypatch.setenv("TEST_PROXY", "http://proxy-1.test")
        manager = SecretManager()

        assert manager.get_credentials().username == "alice"
        assert manager.get_auth_config(api_base_url="https://erp.test/api", env="test").clientid == "client-1"
        assert manager.get_api_login_password_payload() == "encrypted-1"
        assert manager.get_proxy() == "http://proxy-1.test"

        monkeypatch.setenv("TEST_USERNAME", "bob")
        monkeypatch.setenv("TEST_PASSWORD", "changed")
        monkeypatch.setenv("TEST_CLIENTID", "client-2")
        monkeypatch.setenv("TEST_ENCRYPT_KEY", "key-2")
        monkeypatch.setenv("TEST_ENCRYPTED_LOGIN_PASSWORD", "encrypted-2")
        monkeypatch.setenv("TEST_PROXY", "http://proxy-2.test")
        manager.clear_cache()

        assert manager.get_credentials().username == "bob"
        assert manager.get_auth_config(api_base_url="https://erp.test/api", env="test").clientid == "client-2"
        assert manager.get_api_login_password_payload() == "encrypted-2"
        assert manager.get_proxy() == "http://proxy-2.test"


class TestExecutionAuth:
    def setup_method(self):
        reset_singletons()

    def teardown_method(self):
        reset_singletons()

    def test_manager_reads_authorization_from_environment(self, monkeypatch):
        monkeypatch.setenv(execution_auth.AUTHORIZATION_ENV_VAR, execution_auth.AUTHORIZATION_TOKEN)
        monkeypatch.setenv("AUTHORIZED_BY", "qa")
        monkeypatch.setenv("AUTHORIZED_AT", "2026-07-27T10:00:00")

        manager = execution_auth.ExecutionAuthManager()

        assert manager.is_authorized()
        assert manager.get_authorization_status() == {
            "authorized": True,
            "authorized_by": "qa",
            "authorized_at": "2026-07-27T10:00:00",
        }

    def test_check_authorization_raises_when_not_authorized(self, monkeypatch):
        monkeypatch.delenv(execution_auth.AUTHORIZATION_ENV_VAR, raising=False)

        with pytest.raises(execution_auth.ExecutionAuthorizationError):
            execution_auth.check_authorization()

    def test_report_sensitive_operation_raises_report_error(self):
        manager = execution_auth.ExecutionAuthManager()

        with pytest.raises(execution_auth.SensitiveOperationError) as exc:
            manager.report_sensitive_operation("test sku", "delete", ["SKU-1"], "high")

        message = str(exc.value)
        assert "test sku" in message
        assert "delete" in message
        assert "SKU-1" in message


class TestAuthEngine:
    def test_load_matrix_and_expand_cases(self, tmp_path):
        matrix_path = tmp_path / "matrix.yaml"
        matrix_path.write_text(
            yaml.safe_dump(
                {
                    "features": [
                        {
                            "name": "sku",
                            "endpoint": "/sku",
                            "method": "POST",
                            "roles": {"admin": "allow", "guest": "deny"},
                            "data_scope": "own",
                        }
                    ]
                }
            ),
            encoding="utf-8",
        )

        engine = AuthEngine(str(matrix_path))

        assert engine.get_matrix_cases() == [
            {
                "feature": "sku",
                "endpoint": "/sku",
                "method": "POST",
                "role": "admin",
                "expected": "allow",
                "data_scope": "own",
            },
            {
                "feature": "sku",
                "endpoint": "/sku",
                "method": "POST",
                "role": "guest",
                "expected": "deny",
                "data_scope": "own",
            },
        ]

    def test_execute_auth_case_sets_token_and_maps_status_to_allow(self):
        client = SimpleNamespace(
            cleared=False,
            token=None,
            clear_auth=lambda: setattr(client, "cleared", True),
            set_auth_token=lambda token: setattr(client, "token", token),
            get=lambda endpoint: SimpleNamespace(status_code=200),
        )
        engine = AuthEngine()
        engine.register_role_token("admin", "token-1")

        result = engine.execute_auth_case(
            {"feature": "sku", "role": "admin", "endpoint": "/sku", "method": "GET", "expected": "allow"},
            client=client,
        )

        assert client.cleared is True
        assert client.token == "token-1"
        assert result["actual"] == "allow"
        assert result["passed"] is True

    def test_execute_auth_case_maps_request_exception_to_deny(self):
        def failing_get(_endpoint):
            raise requests.RequestException("network blocked")

        client = SimpleNamespace(clear_auth=lambda: None, set_auth_token=lambda token: None, get=failing_get)
        engine = AuthEngine()
        engine.register_role_token("guest", "token-2")

        result = engine.execute_auth_case(
            {"feature": "sku", "role": "guest", "endpoint": "/sku", "method": "GET", "expected": "deny"},
            client=client,
        )

        assert result["status_code"] == 503
        assert result["actual"] == "deny"
        assert result["passed"] is True

    def test_execute_auth_case_requires_registered_role_token(self):
        with pytest.raises(ValueError, match="No token registered"):
            AuthEngine().execute_auth_case({"role": "missing"}, client=SimpleNamespace())


class TestTokenManager:
    def setup_method(self):
        reset_singletons()

    def teardown_method(self):
        reset_singletons()

    def test_load_save_get_and_clear_tokens_use_configured_file(self, tmp_path):
        token_file = tmp_path / "tokens.json"
        token_file.write_text(
            json.dumps(
                {
                    "test": {
                        "token": "old",
                        "env": "test",
                        "username": "alice",
                        "obtained_at": datetime.now().isoformat(),
                        "expires_in": 7200,
                    }
                }
            ),
            encoding="utf-8",
        )
        manager = TokenManager()
        manager._token_file = token_file
        manager._tokens = {}
        manager._load_tokens()

        assert manager.get_token("test") == "old"
        manager.save_token("uat", "new", "bob", expires_in=60)
        assert json.loads(token_file.read_text(encoding="utf-8"))["uat"]["token"] == "new"
        assert manager.get_env_vars("uat")["UAT_USERNAME"] == "bob"
        manager.clear_token("uat")
        assert manager.get_token("uat") is None
        manager.clear_all_tokens()
        assert not token_file.exists()

    def test_expired_or_invalid_token_is_not_returned(self):
        manager = TokenManager()
        manager._tokens = {
            "old": TokenInfo(
                token="expired",
                env="old",
                username="alice",
                obtained_at=(datetime.now() - timedelta(hours=3)).isoformat(),
                expires_in=1,
            ),
            "bad": TokenInfo(token="bad", env="bad", username="bob", obtained_at="not-a-date", expires_in=7200),
        }

        assert manager.get_token("old") is None
        assert manager.get_token("bad") is None

    def test_reset_clears_memory_state_without_deleting_token_file(self, tmp_path):
        token_file = tmp_path / "tokens.json"
        token_file.write_text("{}", encoding="utf-8")
        manager = TokenManager()
        manager._token_file = token_file
        manager._tokens = {
            "test": TokenInfo(
                token="token",
                env="test",
                username="alice",
                obtained_at=datetime.now().isoformat(),
                expires_in=7200,
            )
        }

        TokenManager.reset()

        assert token_file.exists()
        assert TokenManager() is not manager

    def test_clear_token_only_removes_target_environment(self, tmp_path):
        token_file = tmp_path / "tokens.json"
        manager = TokenManager()
        manager._token_file = token_file
        manager._tokens = {
            "test": TokenInfo("test-token", "test", "alice", datetime.now().isoformat()),
            "uat": TokenInfo("uat-token", "uat", "bob", datetime.now().isoformat()),
        }

        manager.clear_token("test")

        assert manager.get_token("test") is None
        assert manager.get_token("uat") == "uat-token"
        persisted = json.loads(token_file.read_text(encoding="utf-8"))
        assert list(persisted) == ["uat"]

    def test_clear_all_tokens_removes_memory_and_persisted_state(self, tmp_path):
        token_file = tmp_path / "tokens.json"
        token_file.write_text("{}", encoding="utf-8")
        manager = TokenManager()
        manager._token_file = token_file
        manager._tokens = {"test": TokenInfo("token", "test", "alice", datetime.now().isoformat())}

        manager.clear_all_tokens()

        assert manager.get_all_tokens() == {}
        assert not token_file.exists()


class TestLoginService:
    def setup_method(self):
        reset_singletons()

    def teardown_method(self):
        reset_singletons()

    def test_login_returns_cached_token_when_valid(self, monkeypatch):
        service = LoginService()
        service._token = "cached"
        service._token_obtain_time = 1000.0
        monkeypatch.setattr("modules.auto_test.core.login_service.time.time", lambda: 1001.0)
        service._auth.login = lambda: pytest.fail("login should not be called")

        result = service.login()

        assert result["success"] is True
        assert result["token"] == "cached"

    def test_login_success_stores_token_and_last_response(self, monkeypatch):
        response = SimpleNamespace(
            status_code=200,
            json=lambda: {"code": 200, "data": {"access_token": "fresh"}},
            raise_for_status=lambda: None,
        )
        service = LoginService()
        service._auth.apply_default_api_headers = lambda env=None: None
        service._auth.login = lambda: response
        monkeypatch.setattr("modules.auto_test.core.login_service.time.time", lambda: 2000.0)

        result = service.login(force=True, env="uat")

        assert result["success"] is True
        assert result["token"] == "fresh"
        assert service.get_login_response() == {"code": 200, "data": {"access_token": "fresh"}}
        assert service.is_logged_in()

    def test_login_handles_business_failure_and_request_exception(self):
        failure_response = SimpleNamespace(
            status_code=200,
            json=lambda: {"code": 401, "msg": "bad credentials"},
            raise_for_status=lambda: None,
        )
        service = LoginService()
        service._auth.apply_default_api_headers = lambda env=None: None
        service._auth.login = lambda: failure_response

        failure = service.login(force=True)
        assert failure == {
            "success": False,
            "token": None,
            "error": "bad credentials",
            "token_obtain_time": None,
            "is_token_valid": False,
        }

        service._auth.login = lambda: (_ for _ in ()).throw(requests.RequestException("timeout"))
        error = service.login(force=True)
        assert error["success"] is False
        assert error["error"] == "timeout"

    def test_clear_token_and_reset_clear_login_state(self):
        service = LoginService()
        service._token = "cached"
        service._token_obtain_time = 1000.0
        service._last_login_response = {"code": 200}

        service.clear_token()

        assert service.get_login_response() is None
        assert not service.is_logged_in()

        service._token = "again"
        LoginService.reset()

        fresh = LoginService()
        assert fresh is not service
        assert fresh.get_token_info()["has_token"] is False

    def test_clear_token_removes_cached_login_state(self):
        service = LoginService()
        service._token = "cached"
        service._token_obtain_time = time.time()

        service.clear_token()

        assert not service.is_logged_in()
        assert service.get_token_info() == {
            "has_token": False,
            "token_valid": False,
            "token_obtain_time": None,
            "elapsed_seconds": None,
        }
