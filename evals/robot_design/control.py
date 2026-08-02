#!/usr/bin/env python3
"""Smallest honest control for the robot-design evaluation POC.

This deliberately omits agent execution, isolation, evidence storage, and profile
management. It only drives the shared task graders over existing artifact trees.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import stat
import sys
from pathlib import Path
from typing import Any, Callable


SCHEMA = "robot-design-control-v1"
REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha256_json(value: Any) -> str:
    return _sha256_bytes(_canonical(value).encode("utf-8"))


def _within(root: Path, relative: str) -> Path:
    candidate = (root.resolve() / relative).resolve(strict=False)
    try:
        candidate.relative_to(root.resolve())
    except ValueError as exc:
        raise ValueError(f"path escapes suite: {relative}") from exc
    return candidate


def _task(suite: Path, task_id: str) -> tuple[dict[str, Any], Path]:
    path = suite.resolve() / "tasks" / task_id / "public" / "task.json"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"invalid task: {task_id}") from exc
    if not isinstance(payload, dict) or payload.get("task_id") != task_id:
        raise ValueError(f"task identity mismatch: {task_id}")
    return payload, path


def _tasks(suite: Path) -> list[str]:
    ids: list[str] = []
    for path in sorted((suite.resolve() / "tasks").glob("*/public/task.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        task_id = payload.get("task_id") if isinstance(payload, dict) else None
        if not isinstance(task_id, str) or not task_id:
            raise ValueError(f"invalid task manifest: {path}")
        ids.append(task_id)
    if not ids or len(ids) != len(set(ids)):
        raise ValueError("suite must contain unique tasks")
    return ids


def _load_grader(path: Path) -> Callable[[Path], Any]:
    namespace: dict[str, Any] = {
        "__file__": str(path),
        "__name__": f"control_grader_{path.parent.name.replace('-', '_')}",
    }
    source = path.read_bytes()
    exec(compile(source, str(path), "exec"), namespace)
    grader = namespace.get("grade")
    if not callable(grader):
        raise ValueError(f"grader has no grade(workspace): {path}")
    return grader


def _artifact_manifest(root: Path) -> list[dict[str, Any]]:
    resolved = root.resolve()
    if not resolved.is_dir():
        raise ValueError(f"artifact root is not a directory: {root}")
    rows: list[dict[str, Any]] = []
    for path in sorted(resolved.rglob("*")):
        if path.is_symlink():
            raise ValueError(f"artifact tree contains symlink: {path}")
        metadata = path.lstat()
        if stat.S_ISDIR(metadata.st_mode):
            continue
        if not stat.S_ISREG(metadata.st_mode):
            raise ValueError(f"artifact tree contains non-regular file: {path}")
        if metadata.st_nlink > 1:
            raise ValueError(f"artifact tree contains hard link: {path}")
        data = path.read_bytes()
        rows.append(
            {
                "path": path.relative_to(resolved).as_posix(),
                "sha256": _sha256_bytes(data),
                "size_bytes": len(data),
            }
        )
    return rows


def _state(grades: list[dict[str, Any]]) -> str:
    statuses = {row.get("status") for row in grades}
    if "error" in statuses:
        return "error"
    if "unrun" in statuses:
        return "unrun"
    if "fail" in statuses:
        return "failed"
    if grades and statuses == {"pass"}:
        return "passed"
    raise ValueError("grader returned an invalid status contract")


def _grade(suite: Path, task_id: str, artifacts: Path) -> dict[str, Any]:
    suite = suite.resolve()
    payload, task_path = _task(suite, task_id)
    grader_path = _within(suite, str(payload["grader_entrypoint"]))
    if not grader_path.is_file() or grader_path.is_symlink():
        raise ValueError(f"grader is missing: {grader_path}")
    manifest = _artifact_manifest(artifacts)
    raw_grades = _load_grader(grader_path)(artifacts.resolve())
    try:
        grades = json.loads(json.dumps(raw_grades))
    except (TypeError, ValueError) as exc:
        raise ValueError("grader output is not JSON-compatible") from exc
    if not isinstance(grades, list) or any(not isinstance(row, dict) for row in grades):
        raise ValueError("grader output must be a list of objects")
    failed = sorted(
        str(row["grade_id"])
        for row in grades
        if row.get("status") == "fail" and isinstance(row.get("grade_id"), str)
    )
    return {
        "schema": SCHEMA,
        "command": "grade",
        "suite_root": str(suite),
        "task_id": task_id,
        "task_version": payload.get("version"),
        "task_digest": _sha256_bytes(task_path.read_bytes()),
        "grader_digest": _sha256_bytes(grader_path.read_bytes()),
        "declared_failure_grade_id": payload.get("seeded_failure_grade_id"),
        "artifact_root": str(artifacts.resolve()),
        "artifact_digest": _sha256_json(manifest),
        "artifact_manifest": manifest,
        "state": _state(grades),
        "failed_grade_ids": failed,
        "grades": grades,
    }


def _validate(args: argparse.Namespace) -> tuple[dict[str, Any], int]:
    suite = Path(args.suite).resolve()
    rows: list[dict[str, Any]] = []
    for task_id in _tasks(suite):
        payload, _ = _task(suite, task_id)
        reference = _grade(suite, task_id, _within(suite, str(payload["reference_dir"])))
        seeded = _grade(
            suite,
            task_id,
            _within(suite, str(payload["seeded_failure_dir"])),
        )
        declared = str(payload["seeded_failure_grade_id"])
        valid = reference["state"] == "passed" and declared in seeded["failed_grade_ids"]
        rows.append(
            {
                "task_id": task_id,
                "reference_state": reference["state"],
                "reference_artifact_digest": reference["artifact_digest"],
                "seeded_failure_state": seeded["state"],
                "seeded_failure_artifact_digest": seeded["artifact_digest"],
                "failed_grade_ids": seeded["failed_grade_ids"],
                "declared_failure_grade_id": declared,
                "valid": valid,
            }
        )
    payload = {
        "schema": SCHEMA,
        "command": "validate",
        "task_count": len(rows),
        "reference_passes": sum(row["reference_state"] == "passed" for row in rows),
        "seeded_failures_caught": sum(row["valid"] for row in rows),
        "tasks": rows,
    }
    return payload, 0 if all(row["valid"] for row in rows) else 1


def _record_rows(path: Path) -> list[dict[str, Any]]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(value, dict) and isinstance(value.get("records"), list):
        value = value["records"]
    elif isinstance(value, dict):
        value = [value]
    if not isinstance(value, list) or any(not isinstance(row, dict) for row in value):
        raise ValueError(f"record file must contain grade objects: {path}")
    return value


def _compare(args: argparse.Namespace) -> tuple[dict[str, Any], int]:
    left_rows = _record_rows(Path(args.left))
    right_rows = _record_rows(Path(args.right))
    left = {(str(row.get("task_id")), int(row.get("attempt", 1))): row for row in left_rows}
    right = {(str(row.get("task_id")), int(row.get("attempt", 1))): row for row in right_rows}
    if set(left) != set(right) or len(left) != len(left_rows) or len(right) != len(right_rows):
        raise ValueError("comparison records have mismatched or duplicate task attempts")
    rows: list[dict[str, Any]] = []
    for task_attempt in sorted(left):
        left_state = left[task_attempt].get("state")
        right_state = right[task_attempt].get("state")
        classification = "unchanged"
        if left_state == "passed" and right_state != "passed":
            classification = "regression"
        elif left_state != "passed" and right_state == "passed":
            classification = "improvement"
        rows.append(
            {
                "task_id": task_attempt[0],
                "attempt": task_attempt[1],
                "left_state": left_state,
                "right_state": right_state,
                "classification": classification,
                "decision_agreement": (
                    left_state == right_state
                    and left[task_attempt].get("failed_grade_ids")
                    == right[task_attempt].get("failed_grade_ids")
                ),
            }
        )
    return {
        "schema": SCHEMA,
        "command": "compare",
        "rows": rows,
        "left_pass_rate": sum(row["left_state"] == "passed" for row in rows) / len(rows),
        "right_pass_rate": sum(row["right_state"] == "passed" for row in rows) / len(rows),
        "improvements": [row["task_id"] for row in rows if row["classification"] == "improvement"],
        "regressions": [row["task_id"] for row in rows if row["classification"] == "regression"],
    }, 0


def _replay_basis(record: dict[str, Any]) -> dict[str, Any]:
    keys = (
        "task_id",
        "task_version",
        "task_digest",
        "grader_digest",
        "artifact_digest",
        "state",
        "failed_grade_ids",
        "grades",
    )
    return {key: record.get(key) for key in keys}


def _replay(args: argparse.Namespace) -> tuple[dict[str, Any], int]:
    original_rows = _record_rows(Path(args.record))
    if len(original_rows) != 1:
        raise ValueError("replay requires exactly one grade record")
    original = original_rows[0]
    original_digest = _sha256_json(_replay_basis(original))
    results = [
        _grade(
            Path(str(original["suite_root"])),
            str(original["task_id"]),
            Path(str(original["artifact_root"])),
        )
        for _ in range(args.repeat)
    ]
    digests = [_sha256_json(_replay_basis(result)) for result in results]
    identical = len(set(digests)) == 1
    matches_record = all(digest == original_digest for digest in digests)
    payload = {
        "schema": SCHEMA,
        "command": "replay",
        "task_id": original.get("task_id"),
        "repeat": args.repeat,
        "original_digest": original_digest,
        "repeat_digests": digests,
        "identical": identical,
        "matches_record": matches_record,
    }
    return payload, 0 if identical and matches_record else 1


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    validate = commands.add_parser("validate")
    validate.add_argument("--suite", required=True)
    validate.set_defaults(handler=_validate)
    grade = commands.add_parser("grade")
    grade.add_argument("--suite", required=True)
    grade.add_argument("--task", required=True)
    grade.add_argument("--artifacts", required=True)
    grade.set_defaults(
        handler=lambda args: (
            _grade(Path(args.suite), args.task, Path(args.artifacts)),
            0,
        )
    )
    compare = commands.add_parser("compare")
    compare.add_argument("--left", required=True)
    compare.add_argument("--right", required=True)
    compare.set_defaults(handler=_compare)
    replay = commands.add_parser("replay")
    replay.add_argument("--record", required=True)
    replay.add_argument("--repeat", type=int, default=3)
    replay.set_defaults(handler=_replay)
    return parser


def main() -> int:
    parser = _parser()
    args = parser.parse_args()
    if getattr(args, "repeat", 1) < 1:
        parser.error("--repeat must be positive")
    try:
        payload, exit_code = args.handler(args)
    except Exception as exc:
        print(_canonical({"schema": SCHEMA, "error": str(exc)}), file=sys.stderr)
        return 2
    print(_canonical(payload))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
