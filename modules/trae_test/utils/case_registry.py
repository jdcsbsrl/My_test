"""Local versioned case register, separate from immutable delivery workbooks."""

from __future__ import annotations

import hashlib
import json
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from .runtime_paths import project_root
from .template_builder import ALL_FIELDS


class CaseRegistry:
    def __init__(self, path: Path | None = None):
        self.path = path or project_root() / "data" / "private" / "case_registry.sqlite3"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as db:
            db.execute("""CREATE TABLE IF NOT EXISTS cases (
                case_id TEXT NOT NULL, version INTEGER NOT NULL, requirement_id TEXT NOT NULL,
                fingerprint TEXT NOT NULL, content TEXT NOT NULL, active INTEGER NOT NULL,
                script_id TEXT NOT NULL DEFAULT '', reason TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL, PRIMARY KEY(case_id, version))""")
            db.execute("""CREATE TABLE IF NOT EXISTS executions (
                case_id TEXT NOT NULL, version INTEGER NOT NULL, status TEXT NOT NULL,
                evidence TEXT NOT NULL, created_at TEXT NOT NULL,
                FOREIGN KEY(case_id, version) REFERENCES cases(case_id, version))""")
            db.execute("""CREATE TABLE IF NOT EXISTS script_snapshots (
                case_id TEXT NOT NULL, version INTEGER NOT NULL, digest TEXT NOT NULL,
                PRIMARY KEY(case_id, version),
                FOREIGN KEY(case_id, version) REFERENCES cases(case_id, version))""")

    @staticmethod
    def script_digest(script_id: str) -> str:
        if not script_id:
            return ""
        path = (project_root() / script_id.split("::", 1)[0]).resolve()
        allowed = (project_root() / "modules/auto_test/tests").resolve()
        if not path.is_relative_to(allowed) or not path.is_file() or path.suffix != ".py":
            return ""
        return hashlib.sha256(path.read_bytes()).hexdigest()

    @contextmanager
    def _connect(self):
        db = sqlite3.connect(self.path)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        try:
            with db:
                yield db
        finally:
            db.close()

    @staticmethod
    def fingerprint(case: dict) -> str:
        # Reference scores change without changing test intent.
        content = {key: case.get(key, "") for key in ALL_FIELDS if key != "质量评分"}
        if case.get("_runtime_rule_binding"):
            content["_runtime_rule_binding"] = case["_runtime_rule_binding"]
        return hashlib.sha256(json.dumps(content, ensure_ascii=False, sort_keys=True).encode()).hexdigest()

    def list_cases(self, requirement_id: str | None = None, *, active_only: bool = True) -> list[dict]:
        clauses, values = [], []
        if active_only:
            clauses.append("active=1")
        if requirement_id is not None:
            clauses.append("requirement_id=?")
            values.append(requirement_id)
        sql = """SELECT cases.*,
            (SELECT status FROM executions e WHERE e.case_id=cases.case_id AND e.version=cases.version
             ORDER BY e.rowid DESC LIMIT 1) AS last_status,
            (SELECT evidence FROM executions e WHERE e.case_id=cases.case_id AND e.version=cases.version
             ORDER BY e.rowid DESC LIMIT 1) AS last_evidence
            ,(SELECT created_at FROM executions e WHERE e.case_id=cases.case_id AND e.version=cases.version
             ORDER BY e.rowid DESC LIMIT 1) AS last_executed_at
            ,(SELECT digest FROM script_snapshots s WHERE s.case_id=cases.case_id AND s.version=cases.version)
             AS script_digest
            FROM cases""" + (" WHERE " + " AND ".join(clauses) if clauses else "")
        with self._connect() as db:
            rows = db.execute(sql + " ORDER BY case_id,version", values).fetchall()
        return [{**dict(row), "content": json.loads(row["content"])} for row in rows]

    def propose(self, cases: list[dict], requirement_id: str) -> list[dict]:
        existing = self.list_cases(requirement_id)
        suggestions = []
        seen = set()
        for index, case in enumerate(cases):
            digest = self.fingerprint(case)
            match = next((row for row in existing if row["fingerprint"] == digest), None)
            candidates = [row["case_id"] for row in existing if row["content"].get("用例名称") == case.get("用例名称")]
            action = "reuse" if match else "review_update" if candidates else "new"
            if digest in seen:
                action = "duplicate"
            seen.add(digest)
            suggestions.append(
                {
                    "index": index,
                    "action": action,
                    "case_id": match["case_id"] if match else None,
                    "candidate_ids": candidates,
                }
            )
        return suggestions

    def save(
        self, case: dict, requirement_id: str, *, case_id: str | None = None, script_id: str = "", reason: str = ""
    ) -> tuple[str, int]:
        if not requirement_id.strip():
            raise ValueError("A stable requirement ID is required for registration")
        if case.get("需求ID") != requirement_id:
            raise ValueError("Case requirement ID does not match registration scope")
        from .runtime_quality import read_runtime_quality

        quality = read_runtime_quality(case)
        if not quality.final_audit_passed or quality.needs_human_review:
            raise ValueError("Only audited cases can become active")
        digest = self.fingerprint(case)
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            match = db.execute(
                "SELECT case_id,version,script_id FROM cases WHERE requirement_id=? AND fingerprint=? AND active=1",
                (requirement_id, digest),
            ).fetchone()
            snapshot = (
                db.execute(
                    "SELECT digest FROM script_snapshots WHERE case_id=? AND version=?",
                    (match["case_id"], match["version"]),
                ).fetchone()
                if match
                else None
            )
            script_unchanged = not script_id or (snapshot and snapshot[0] == self.script_digest(script_id))
            if (
                match
                and script_unchanged
                and (
                    not case_id or (case_id == match["case_id"] and (not script_id or script_id == match["script_id"]))
                )
            ):
                return match["case_id"], match["version"]
            if match and case_id != match["case_id"]:
                raise ValueError("Matching content belongs to another active case; review reuse before updating")
            version = 1
            if case_id:
                old = db.execute("SELECT * FROM cases WHERE case_id=? AND active=1", (case_id,)).fetchone()
                if not old or old["requirement_id"] != requirement_id or not reason.strip():
                    raise ValueError("Updating requires an active matching case and a reason")
                version = old["version"] + 1
                script_id = script_id or old["script_id"]
                db.execute("UPDATE cases SET active=0 WHERE case_id=?", (case_id,))
            else:
                # A title collision is an update candidate, never silently activated as another case.
                rows = db.execute(
                    "SELECT content FROM cases WHERE requirement_id=? AND active=1", (requirement_id,)
                ).fetchall()
                if any(json.loads(row[0]).get("用例名称") == case.get("用例名称") for row in rows):
                    raise ValueError("Existing title: specify case_id and reason to update")
                case_id = "TC-" + uuid.uuid4().hex
            saved = {key: case[key] for key in ALL_FIELDS}
            if case.get("_runtime_rule_binding"):
                saved["_runtime_rule_binding"] = case["_runtime_rule_binding"]
            content = json.dumps(saved, ensure_ascii=False)
            db.execute(
                "INSERT INTO cases VALUES (?,?,?,?,?,?,?,?,?)",
                (
                    case_id,
                    version,
                    requirement_id,
                    digest,
                    content,
                    1,
                    script_id,
                    reason,
                    datetime.now(timezone.utc).isoformat(),
                ),
            )
            db.execute("INSERT INTO script_snapshots VALUES (?,?,?)", (case_id, version, self.script_digest(script_id)))
        return case_id, version

    def retire(self, case_id: str, reason: str) -> None:
        if not reason.strip():
            raise ValueError("Retirement requires a reason")
        with self._connect() as db:
            cursor = db.execute("UPDATE cases SET active=0,reason=? WHERE case_id=? AND active=1", (reason, case_id))
            if cursor.rowcount != 1:
                raise ValueError("Active case not found")

    def record_execution(self, case_id: str, version: int, status: str, evidence: str) -> None:
        if status not in {"PASS", "FAIL", "SKIP", "BLOCKED"} or not evidence.strip():
            raise ValueError("Execution status and evidence are required")
        with self._connect() as db:
            db.execute(
                "INSERT INTO executions VALUES (?,?,?,?,?)",
                (case_id, version, status, evidence, datetime.now(timezone.utc).isoformat()),
            )
