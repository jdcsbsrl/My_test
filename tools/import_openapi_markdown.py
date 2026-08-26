"""Convert a Widdershins Markdown export into searchable KB business rules."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

METHOD_RE = re.compile(r"^(GET|POST|PUT|DELETE|PATCH|OPTIONS|HEAD)\s+(\S+)", re.MULTILINE)
HEADING_RE = re.compile(r"^##\s+(.+?)\s*$", re.MULTILINE)
NOISE_RE = re.compile(r"^(\[|\{|\}|\]|```|注意[:：]|参数[:：]|请求参数|响应参数)")


def convert(source: Path, target: Path) -> int:
    text = source.read_text(encoding="utf-8")
    rules: list[dict[str, object]] = []
    matches = list(METHOD_RE.finditer(text))

    for index, match in enumerate(matches, start=1):
        start = match.start()
        end = matches[index].start() if index < len(matches) else len(text)
        section = text[start:end]
        heading = ""
        for heading_match in HEADING_RE.finditer(text[:start]):
            heading = heading_match.group(1).strip()
        description = ""
        lines = section.splitlines()[1:]
        for line in lines:
            value = line.strip()
            cleaned = value.lstrip("- *")
            punctuation_only = sum(char in "{}[](),:;\"'" for char in cleaned) >= max(1, len(cleaned) // 2)
            if (
                value
                and len(value) >= 2
                and not value.startswith("#")
                and not value.startswith(">")
                and not value.startswith("`")
                and not NOISE_RE.match(value)
                and not (value.startswith('"') and value.endswith((",", ":")))
                and not value.startswith('"')
                and not value.startswith("|")
                and value.count("|") < 2
                and not cleaned.startswith(("{", "["))
                and not punctuation_only
            ):
                description = value
                break
        method, path = match.groups()
        rules.append(
            {
                "rule_id": f"OPENAPI-{index:06d}",
                "name": heading or f"{method} {path}",
                "title": heading or f"{method} {path}",
                "method": method,
                "path": path,
                "description": description,
                "source": source.name,
            }
        )

    payload = {
        "title": "默认模块接口知识",
        "source_file": source.name,
        "source_format": "widdershins-markdown",
        "business_rules": rules,
        "statistics": {"endpoint_count": len(rules)},
    }
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"转换完成: {len(rules)} 个接口 -> {target}")
    return len(rules)


def main() -> int:
    parser = argparse.ArgumentParser(description="将 Widdershins Markdown 转为可检索接口业务知识")
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--target", required=True, type=Path)
    args = parser.parse_args()
    if not args.source.exists():
        parser.error(f"源文件不存在: {args.source}")
    return 0 if convert(args.source, args.target) else 1


if __name__ == "__main__":
    raise SystemExit(main())
