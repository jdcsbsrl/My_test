import os
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent

SENSITIVE_PATTERNS = {
    "hardcoded_password": re.compile(r'password["\']?\s*[:=]\s*["\']\d{4,}'),
    "hardcoded_phone": re.compile(r'["\']1[3-9]\d{9}["\']'),
    "hardcoded_url_with_domain": re.compile(r'["\']https?://(erptest|erpuat|api\.dayonefulfillment)\.dayoneerp\.com'),
    "app_key_pattern": re.compile(r'["\']ak_[a-z0-9]{10,}["\']'),
    "app_secret_pattern": re.compile(r'["\']sk_[a-z0-9]{10,}["\']'),
}

TRACKED_FILES_TO_SKIP = {
    "tests/unit/test_audit_agent.py",
    "modules/trae_test/orchestrator/audit_agent_enhanced.py",
    ".secrets.baseline",
}

def main() -> int:
    errors = []
    
    result = os.popen("git ls-files").read().splitlines()
    
    for filepath in result:
        if filepath in TRACKED_FILES_TO_SKIP:
            continue
        file_path = REPO_ROOT / filepath
        if not file_path.exists():
            continue
        try:
            content = file_path.read_text(encoding="utf-8", errors="ignore")
            for pattern_name, pattern in SENSITIVE_PATTERNS.items():
                matches = pattern.findall(content)
                if matches:
                    errors.append(f"[{pattern_name}] {filepath}: {matches[:3]}")
        except Exception as e:
            print(f"Error reading {filepath}: {e}")
    
    if errors:
        print("❌ 以下文件仍包含敏感信息：")
        for e in errors:
            print(f"  {e}")
        return 1
    else:
        print("✅ 未检测到硬编码敏感信息，可以安全转为公有仓库")
        return 0

if __name__ == "__main__":
    sys.exit(main())
