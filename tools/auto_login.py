"""自动登录工具，用于验证 UAT 和 TEST 环境的登录状态。"""

import sys
from collections.abc import Mapping
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(errors="replace")

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root / "modules" / "auto_test"))

from modules.auto_test.core.config_manager import ConfigManager, get_config
from modules.auto_test.core.environment import validate_environment
from modules.auto_test.core.login_service import get_login_service
from modules.auto_test.core.secret_manager import get_secret_manager
from modules.auto_test.core.token_manager import get_token_manager


def _safe_var_metadata(value: object) -> dict[str, bool | int]:
    """Return only non-sensitive metadata for an environment variable."""
    if isinstance(value, Mapping) and {"exists", "length"}.issubset(value):
        return {
            "exists": bool(value["exists"]),
            "length": int(value["length"]),
        }
    return {
        "exists": value is not None,
        "length": len(str(value)) if value is not None else 0,
    }


def _summarize_env_vars(values: Mapping[object, object]) -> dict[str, dict[str, bool | int]]:
    """Convert raw environment variables into a safe, value-free summary."""
    if not isinstance(values, Mapping):
        return {}
    return {str(key): _safe_var_metadata(value) for key, value in values.items()}


def login_to_env(env: str, force: bool = False) -> dict:
    """登录到指定环境并返回不含认证字段的最小状态。"""
    print(f"\n{'='*60}")
    print(f"登录 {env.upper()} 环境")
    print(f"{'='*60}")

    try:
        # 验证环境
        validate_environment(env)
        print("✓ 环境验证通过")

        # 重置配置
        ConfigManager.reset()

        # 加载配置
        get_config(env)
        print("✓ 配置加载成功")

        # Fail with a safe, actionable preflight result before making a request.
        secret_manager = get_secret_manager()
        secret_manager.get_credentials()
        secret_manager.get_auth_config(env=env)
        print("✓ 登录配置预检通过")

        # 获取登录服务
        login_service = get_login_service()

        # 登录
        print("\n正在尝试登录...")
        result = login_service.login(force=force, env=env)

        if isinstance(result, Mapping) and result.get("success") is True:
            print("✓ 登录成功！")
            return {"success": True, "env": env}

        print("✗ 登录失败")
        return {"success": False, "env": env, "error": "登录失败"}

    except Exception:
        # Do not print exception text: server/client errors can echo credentials.
        print("✗ 登录过程出错")
        return {"success": False, "env": env, "error": "登录过程出错"}


def get_env_vars(env: str | None = None) -> dict:
    """获取指定环境变量的安全摘要，如未指定则获取所有环境。"""
    token_manager = get_token_manager()

    if env:
        return _summarize_env_vars(token_manager.get_env_vars(env))

    # 获取所有环境的变量
    all_vars = {}
    for e in ["test", "uat"]:
        all_vars.update(token_manager.get_env_vars(e))
    return _summarize_env_vars(all_vars)


def main():
    """主函数。"""
    import argparse

    parser = argparse.ArgumentParser(description="自动登录工具")
    parser.add_argument(
        "--env", type=str, choices=["test", "uat", "all"], default="all", help="要登录的环境 (默认: all)"
    )
    parser.add_argument("--force", action="store_true", help="强制重新登录，忽略缓存的 token")
    parser.add_argument("--show-vars", action="store_true", help="显示获取到的环境变量")

    args = parser.parse_args()

    print("\n🔐 ERP 自动登录工具")
    print("=" * 60)

    results = []

    if args.env == "all":
        results.append(login_to_env("test", args.force))
        results.append(login_to_env("uat", args.force))
    else:
        results.append(login_to_env(args.env, args.force))

    # 显示结果汇总
    print(f"\n{'='*60}")
    print("登录结果汇总")
    print(f"{'='*60}")

    for result in results:
        status = "✓ 成功" if result["success"] else "✗ 失败"
        print(f"{result['env'].upper()}: {status}")
        if not result["success"] and "error" in result:
            print(f"  错误: {result['error']}")

    # 显示环境变量
    if args.show_vars:
        print(f"\n{'='*60}")
        print("环境变量")
        print(f"{'='*60}")
        for key, metadata in _summarize_env_vars(get_env_vars()).items():
            print(f"{key}: exists={metadata['exists']}, length={metadata['length']}")

    print(f"\n{'='*60}")
    print("完成")
    print(f"{'='*60}")

    if not all(result["success"] for result in results):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
