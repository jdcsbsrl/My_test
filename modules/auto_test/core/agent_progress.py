"""Read and validate `.agents/progress.json` (structured feature tracking)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


_PROGRESS_REL = Path(".agents") / "progress.json"
_SCHEMA_REL = Path(".agents") / "progress.schema.json"


def progress_path(root: Path | None = None) -> Path:
    return (root or _repo_root()) / _PROGRESS_REL


def schema_path(root: Path | None = None) -> Path:
    return (root or _repo_root()) / _SCHEMA_REL


def load_progress_json(root: Path | None = None) -> dict[str, Any]:
    p = progress_path(root)
    if not p.is_file():
        return {}
    with p.open(encoding="utf-8") as f:
        return json.load(f)


def validate_progress(data: dict[str, Any], root: Path | None = None) -> list[str]:
    """Return a list of human-readable errors (empty if OK)."""
    errors: list[str] = []
    if not data:
        errors.append("progress.json missing or empty")
        return errors
    if int(data.get("schema_version", 0)) < 1:
        errors.append("schema_version must be >= 1")

    features = data.get("features")
    if not isinstance(features, list):
        errors.append("'features' must be a list")
        return errors

    allowed_status = {"planned", "in_progress", "done", "blocked", "deferred"}
    allowed_phase = {"initialization", "coding", "shared"}
    ids: set[str] = set()
    for i, feat in enumerate(features):
        if not isinstance(feat, dict):
            errors.append(f"features[{i}] must be an object")
            continue
        fid = feat.get("id")
        if not isinstance(fid, str) or not fid.strip():
            errors.append(f"features[{i}].id required")
        elif fid in ids:
            errors.append(f"duplicate feature id: {fid}")
        else:
            ids.add(fid)
        st = feat.get("status", "planned")
        if st not in allowed_status:
            errors.append(f"features[{i}].status invalid: {st}")
        ph = feat.get("phase", "shared")
        if ph not in allowed_phase:
            errors.append(f"features[{i}].phase invalid: {ph}")

    events = data.get("events", [])
    if events is not None and not isinstance(events, list):
        errors.append("'events' must be a list when present")

    sp = schema_path(root)
    if sp.is_file():
        try:
            import jsonschema  # type: ignore[import-untyped]

            with sp.open(encoding="utf-8") as f:
                schema = json.load(f)
            jsonschema.validate(instance=data, schema=schema)
        except Exception as exc:  # noqa: BLE001 — surface validation message
            errors.append(f"jsonschema: {exc}")

    return errors


def progress_summary(data: dict[str, Any]) -> dict[str, Any]:
    feats = data.get("features", []) if isinstance(data.get("features"), list) else []
    by_status: dict[str, int] = {}
    for f in feats:
        if not isinstance(f, dict):
            continue
        st = str(f.get("status", "planned"))
        by_status[st] = by_status.get(st, 0) + 1
    return {"feature_count": len(feats), "by_status": by_status}
