"""自动登录工具，用于获取 UAT 和 TEST 环境的 token 并保存为环境变量。"""

import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(errors="replace")

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root / "modules" / "auto_test"))

from modules.auto_test.core.config_manager import ConfigManager, get_config
from modules.auto_test.core.environment import validate_environment
from modules.auto_test.core.logger import get_logger
from modules.auto_test.core.login_service import get_login_service
from modules.auto_test.core.token_manager import get_token_manager

logger = get_logger()


def login_to_env(env: str, force: bool = False) -> dict:
    """登录到指定环境并获取 token。"""
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
        config = get_config(env)
        print("✓ 配置加载成功")
        print(f"  API 地址: {config.api_base_url}")

        # 获取登录服务
        login_service = get_login_service()

        # 登录
        print("\n正在尝试登录...")
        result = login_service.login(force=force)

        if result["success"]:
            print("✓ 登录成功！")
            print(f"  Token: {result['token'][:50]}..." if result["token"] else "")

            # 获取登录响应
            response = login_service.get_login_response()
            if response:
                print("\n登录响应已收到（敏感字段已隐藏）")

            return {"success": True, "env": env, "token": result["token"], "response": response}
        else:
            print(f"✗ 登录失败: {result['error']}")
            return {"success": False, "env": env, "error": result["error"]}

    except Exception as e:
        print(f"✗ 登录过程出错: {e}")
        import traceback

        traceback.print_exc()
        return {"success": False, "env": env, "error": str(e)}


def get_env_vars(env: str | None = None) -> dict:
    """获取指定环境的环境变量，如未指定则获取所有环境。"""
    token_manager = get_token_manager()

    if env:
        return token_manager.get_env_vars(env)

    # 获取所有环境的变量
    all_vars = {}
    for e in ["test", "uat"]:
        all_vars.update(token_manager.get_env_vars(e))
    return all_vars


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
        env_vars = get_env_vars()
        for key, value in env_vars.items():
            if "TOKEN" in key and len(value) > 50:
                value = value[:50] + "..."
            print(f"{key}={value}")

    print(f"\n{'='*60}")
    print("完成")
    print(f"{'='*60}")

    if not all(result["success"] for result in results):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
