from typing import Any

import yaml
from requests import RequestException

from modules.auto_test.core.api_client import APIClient
from modules.auto_test.core.logger import get_logger

logger = get_logger()


class AuthEngine:
    def __init__(self, matrix_path: str | None = None) -> None:
        self.matrix: dict[str, Any] = {}
        self.role_tokens: dict[str, str] = {}
        if matrix_path:
            self.load_matrix(matrix_path)

    def load_matrix(self, path: str) -> None:
        with open(path, encoding="utf-8") as f:
            self.matrix = yaml.safe_load(f)
        logger.info(f"Auth matrix loaded from {path}")

    def register_role_token(self, role: str, token: str) -> None:
        self.role_tokens[role] = token
        logger.info(f"Token registered for role: {role}")

    def get_matrix_cases(self) -> list[dict[str, Any]]:
        cases = []
        features = self.matrix.get("features", [])
        for feature in features:
            feature_name = feature["name"]
            endpoint = feature.get("endpoint", "")
            method = feature.get("method", "GET")
            roles = feature.get("roles", {})
            data_scope = feature.get("data_scope", None)

            for role, permission in roles.items():
                cases.append(
                    {
                        "feature": feature_name,
                        "endpoint": endpoint,
                        "method": method,
                        "role": role,
                        "expected": permission,
                        "data_scope": data_scope,
                    }
                )
        return cases

    def execute_auth_case(self, case: dict[str, Any], client: APIClient | None = None) -> dict[str, Any]:
        if client is None:
            client = APIClient()

        role = case["role"]
        token = self.role_tokens.get(role)
        if not token:
            raise ValueError(f"No token registered for role: {role}")

        client.clear_auth()
        client.set_auth_token(token)

        method = case["method"].lower()
        endpoint = case["endpoint"]
        expected = case["expected"]

        try:
            response = getattr(client, method)(endpoint)
            status_code = response.status_code
        except RequestException as e:
            logger.warning(f"Auth check request failed: {case['feature']} | role={role} | error={e}")
            status_code = 503

        actual = "allow" if status_code < 400 else "deny"
        passed = actual == expected

        result = {
            "feature": case["feature"],
            "role": role,
            "endpoint": endpoint,
            "method": case["method"],
            "expected": expected,
            "actual": actual,
            "status_code": status_code,
            "passed": passed,
        }

        if not passed:
            logger.warning(
                f"Auth check FAILED: {case['feature']} | role={role} | "
                f"expected={expected} but got {actual} (HTTP {status_code})"
            )
        else:
            logger.info(f"Auth check PASSED: {case['feature']} | role={role} | {expected}")

        return result

    def run_all(self, client: APIClient | None = None) -> list[dict[str, Any]]:
        results = []
        for case in self.get_matrix_cases():
            result = self.execute_auth_case(case, client)
            results.append(result)
        return results
