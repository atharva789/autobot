"""Backfill imported Langfuse trace observations as LangSmith child runs.

The first Langfuse recovery pass imported each backup trace as one LangSmith
root run. This script replays the original Langfuse observations under those
roots so LangSmith exposes graph-node, tool-call, and agent-call spans.
"""

from __future__ import annotations

import argparse
import json
import os
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID

from dotenv import load_dotenv
from langsmith import Client
from langsmith.run_trees import RunTree, uuid7_deterministic

from packages.research.agent_loops.grammar_loop import STRUCTURAL_RULE_GRAPH_NODES
from packages.research.experiment.run_debug import LangfuseTraceReader

DEFAULT_PROJECT_NAME = "autonomous-robot-codesign"
LANGFUSE_IMPORT_FILTER = 'and(eq(is_root, true), has(tags, "langfuse-import"))'
BACKFILL_VERSION = "2026-05-24.v1"
AGENT_LOOP_MODULE = "packages.research.agent_loops.grammar_loop"

LANGFUSE_TYPE_TO_LANGSMITH_RUN_TYPE: dict[str, str] = {
    "AGENT": "chain",
    "CHAIN": "chain",
    "EVALUATOR": "chain",
    "SPAN": "chain",
    "TOOL": "tool",
    "GENERATION": "llm",
    "EVENT": "chain",
}


@dataclass(frozen=True)
class BackfillStats:
    roots_seen: int = 0
    roots_updated: int = 0
    child_runs_created: int = 0
    child_runs_updated: int = 0
    skipped_children: int = 0

    def merge(self, other: "BackfillStats") -> "BackfillStats":
        return BackfillStats(
            roots_seen=self.roots_seen + other.roots_seen,
            roots_updated=self.roots_updated + other.roots_updated,
            child_runs_created=self.child_runs_created + other.child_runs_created,
            child_runs_updated=self.child_runs_updated + other.child_runs_updated,
            skipped_children=self.skipped_children + other.skipped_children,
        )


def main() -> None:
    args = _parse_args()
    load_dotenv(args.env_path, override=False)

    project_name = args.project_name or os.environ.get("LANGSMITH_PROJECT") or DEFAULT_PROJECT_NAME
    client = Client()
    _disable_buffered_run_ingest(client)
    langfuse_reader = LangfuseTraceReader(env_path=args.env_path)

    stats = backfill_imported_langfuse_traces(
        client=client,
        langfuse_reader=langfuse_reader,
        project_name=project_name,
        dry_run=not args.apply,
        update_roots=args.update_roots,
        update_children=args.update_children,
        limit=args.limit,
        langfuse_trace_id=args.langfuse_trace_id,
    )
    mode = "DRY RUN" if not args.apply else "APPLIED"
    print(
        f"{mode}: roots_seen={stats.roots_seen} roots_updated={stats.roots_updated} "
        f"child_runs_created={stats.child_runs_created} "
        f"child_runs_updated={stats.child_runs_updated} "
        f"skipped_children={stats.skipped_children}"
    )


def backfill_imported_langfuse_traces(
    *,
    client: Client,
    langfuse_reader: LangfuseTraceReader,
    project_name: str,
    dry_run: bool = True,
    update_roots: bool = False,
    update_children: bool = False,
    limit: int | None = None,
    langfuse_trace_id: str | None = None,
) -> BackfillStats:
    _disable_buffered_run_ingest(client)
    roots = list(
        client.list_runs(
            project_name=project_name,
            filter=LANGFUSE_IMPORT_FILTER,
            limit=min(max(limit or 100, 1), 100),
        )
    )
    roots.sort(key=lambda run: _cloud_time(getattr(run, "start_time", None)))

    stats = BackfillStats()
    for root in roots:
        root_metadata = _run_metadata(root)
        source_trace_id = _string_or_none(root_metadata.get("langfuse_trace_id"))
        if not source_trace_id:
            continue
        if langfuse_trace_id and source_trace_id != langfuse_trace_id:
            continue

        trace = langfuse_reader.fetch_trace(source_trace_id)
        observations = [
            obs for obs in trace.get("observations", []) if isinstance(obs, dict)
        ]
        if not observations:
            continue
        stats = stats.merge(
            _backfill_one_root(
                client=client,
                project_name=project_name,
                root=root,
                observations=observations,
                dry_run=dry_run,
                update_roots=update_roots,
                update_children=update_children,
            )
        )
    return stats


def _backfill_one_root(
    *,
    client: Client,
    project_name: str,
    root: Any,
    observations: list[dict[str, Any]],
    dry_run: bool,
    update_roots: bool,
    update_children: bool,
) -> BackfillStats:
    root_id = UUID(str(getattr(root, "id")))
    root_trace_id = UUID(str(getattr(root, "trace_id") or root_id))
    root_dotted_order = str(getattr(root, "dotted_order", "") or "")
    root_start = datetime.now(timezone.utc)
    root_observation = _root_observation(observations)
    root_observation_id = _string_or_none(root_observation.get("id")) if root_observation else None
    original_root_start = _parse_time(root_observation.get("startTime")) if root_observation else None

    existing_runs = {
        str(getattr(run, "id")): run
        for run in client.list_runs(
            project_name=project_name,
            trace_id=root_trace_id,
            limit=100,
        )
    }

    roots_updated = 0
    if update_roots:
        root_update = _root_update_payload(
            root=root,
            root_observation=root_observation,
            mapped_start=root_start,
            original_root_start=original_root_start,
        )
        roots_updated = 1
        if not dry_run:
            client.update_run(root_id, **root_update)

    observation_to_run: dict[str, tuple[UUID, str]] = {}
    if root_observation_id:
        observation_to_run[root_observation_id] = (root_id, root_dotted_order)

    created = 0
    updated = 0
    skipped = 0
    for observation in sorted(observations, key=_observation_sort_key):
        observation_id = _string_or_none(observation.get("id"))
        if not observation_id:
            skipped += 1
            continue
        if observation_id == root_observation_id:
            continue

        parent_observation_id = _string_or_none(observation.get("parentObservationId"))
        parent_id, parent_dotted_order = observation_to_run.get(
            parent_observation_id or "",
            (root_id, root_dotted_order),
        )
        if not parent_dotted_order:
            skipped += 1
            continue

        child_run = _child_run_tree(
            project_name=project_name,
            root_trace_id=root_trace_id,
            root_start=root_start,
            original_root_start=original_root_start,
            root_id=root_id,
            parent_id=parent_id,
            parent_dotted_order=parent_dotted_order,
            observation=observation,
        )
        observation_to_run[observation_id] = (child_run.id, child_run.dotted_order)
        run_payload = child_run._get_dicts_safe()
        child_id = str(child_run.id)
        if child_id in existing_runs:
            if update_children:
                updated += 1
                if not dry_run:
                    client.update_run(
                        child_run.id,
                        name=child_run.name,
                        run_type=child_run.run_type,
                        start_time=child_run.start_time,
                        end_time=child_run.end_time,
                        inputs=child_run.inputs,
                        outputs=child_run.outputs,
                        error=child_run.error,
                        extra=child_run.extra,
                        tags=child_run.tags,
                    )
            else:
                skipped += 1
        else:
            created += 1
            if not dry_run:
                client.create_run(**run_payload)

    if not any(observation.get("name") == "summarize_hitl" for observation in observations):
        summarize_run = _synthetic_summarize_hitl_run_tree(
            project_name=project_name,
            root=root,
            root_trace_id=root_trace_id,
            root_id=root_id,
            root_dotted_order=root_dotted_order,
        )
        summarize_id = str(summarize_run.id)
        if summarize_id in existing_runs:
            skipped += 1
        else:
            created += 1
            if not dry_run:
                client.create_run(**summarize_run._get_dicts_safe())

    return BackfillStats(
        roots_seen=1,
        roots_updated=roots_updated,
        child_runs_created=created,
        child_runs_updated=updated,
        skipped_children=skipped,
    )


def _synthetic_summarize_hitl_run_tree(
    *,
    project_name: str,
    root: Any,
    root_trace_id: UUID,
    root_id: UUID,
    root_dotted_order: str,
) -> RunTree:
    start_time = datetime.now(timezone.utc)
    root_metadata = _run_metadata(root)
    root_outputs = getattr(root, "outputs", None) or {}
    root_inputs = getattr(root, "inputs", None) or {}
    metadata = {
        "source": "langfuse-backfill",
        "langfuse_backfill_version": BACKFILL_VERSION,
        "agent_loop_module": AGENT_LOOP_MODULE,
        "synthetic_span": True,
        "synthetic_reason": "Langfuse backup root output contains HITL summary but no separate summarize_hitl observation.",
        "langfuse_trace_id": root_metadata.get("langfuse_trace_id"),
        "langfuse_observation_id": f"synthetic:{root_id}:summarize_hitl",
        "langfuse_parent_observation_id": root_metadata.get("langfuse_observation_id"),
        "span_kind": "graph_node",
        "span_roles": ["graph_node"],
        "grammar_loop_node": "summarize_hitl",
        "langgraph_node": "summarize_hitl",
    }
    return RunTree(
        id=uuid7_deterministic(root_id, f"synthetic:summarize_hitl:{BACKFILL_VERSION}"),
        name="summarize_hitl",
        run_type="chain",
        inputs=root_inputs if isinstance(root_inputs, dict) else {"input": root_inputs},
        outputs=root_outputs if isinstance(root_outputs, dict) else {"output": root_outputs},
        start_time=start_time,
        end_time=start_time + timedelta(milliseconds=1),
        parent_run_id=root_id,
        parent_dotted_order=root_dotted_order,
        trace_id=root_trace_id,
        project_name=project_name,
        extra={"metadata": metadata},
        tags=["langfuse-import", "langfuse-backfill", "il-ideation"],
    )


def _root_update_payload(
    *,
    root: Any,
    root_observation: dict[str, Any] | None,
    mapped_start: datetime,
    original_root_start: datetime | None,
) -> dict[str, Any]:
    existing_extra = dict(getattr(root, "extra", None) or {})
    existing_metadata = dict((existing_extra.get("metadata") or {}))
    tags = sorted(set(getattr(root, "tags", None) or []) | {"langfuse-backfill"})
    if root_observation is None:
        metadata = {
            **existing_metadata,
            "langfuse_backfill_version": BACKFILL_VERSION,
            "agent_loop_module": AGENT_LOOP_MODULE,
            "span_kind": "agent_call",
        }
        return {
            "start_time": mapped_start,
            "end_time": mapped_start,
            "extra": {**existing_extra, "metadata": metadata},
            "tags": tags,
        }

    metadata = _observation_metadata(root_observation, existing_metadata=existing_metadata)
    end_time = _mapped_time(
        root_observation.get("endTime"),
        root_start=mapped_start,
        original_root_start=original_root_start,
    )
    return {
        "start_time": mapped_start,
        "inputs": _io_payload(root_observation.get("input"), field_name="input"),
        "outputs": _io_payload(root_observation.get("output"), field_name="output"),
        "end_time": end_time,
        "error": _error_for_observation(root_observation),
        "extra": {**existing_extra, "metadata": metadata},
        "tags": tags,
    }


def _child_run_tree(
    *,
    project_name: str,
    root_trace_id: UUID,
    root_start: datetime,
    original_root_start: datetime | None,
    root_id: UUID,
    parent_id: UUID,
    parent_dotted_order: str,
    observation: dict[str, Any],
) -> RunTree:
    start_time = _mapped_time(
        observation.get("startTime"),
        root_start=root_start,
        original_root_start=original_root_start,
    )
    end_time = _mapped_time(
        observation.get("endTime"),
        root_start=root_start,
        original_root_start=original_root_start,
    )
    observation_id = str(observation["id"])
    child_id = uuid7_deterministic(root_id, f"{observation_id}:{BACKFILL_VERSION}")
    name = str(observation.get("name") or "langfuse_observation")
    return RunTree(
        id=child_id,
        name=name,
        run_type=_langsmith_run_type(observation),
        inputs=_io_payload(observation.get("input"), field_name="input"),
        outputs=_io_payload(observation.get("output"), field_name="output"),
        error=_error_for_observation(observation),
        start_time=start_time,
        end_time=end_time,
        parent_run_id=parent_id,
        parent_dotted_order=parent_dotted_order,
        trace_id=root_trace_id,
        project_name=project_name,
        extra={"metadata": _observation_metadata(observation)},
        tags=["langfuse-import", "langfuse-backfill", "il-ideation"],
    )


def _observation_metadata(
    observation: dict[str, Any],
    *,
    existing_metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    metadata = dict(existing_metadata or {})
    source_metadata = observation.get("metadata")
    if isinstance(source_metadata, dict):
        metadata.update(source_metadata)

    name = str(observation.get("name") or "")
    langfuse_type = str(observation.get("type") or "").upper()
    metadata.update(
        {
            "source": "langfuse-backfill",
            "langfuse_backfill_version": BACKFILL_VERSION,
            "agent_loop_module": AGENT_LOOP_MODULE,
            "langfuse_trace_id": observation.get("traceId"),
            "langfuse_observation_id": observation.get("id"),
            "langfuse_parent_observation_id": observation.get("parentObservationId"),
            "langfuse_type": langfuse_type,
            "langfuse_start_time": observation.get("startTime"),
            "langfuse_end_time": observation.get("endTime"),
            "langfuse_level": observation.get("level"),
            "langfuse_status_message": observation.get("statusMessage"),
        }
    )
    if name in STRUCTURAL_RULE_GRAPH_NODES:
        metadata["span_kind"] = "graph_node"
        metadata["grammar_loop_node"] = name
        metadata.setdefault("langgraph_node", name)
        metadata["span_roles"] = ["graph_node"]
    elif langfuse_type == "TOOL":
        metadata["span_kind"] = "tool_call"
        metadata["tool_name"] = name
        metadata["span_roles"] = ["tool_call"]
    elif langfuse_type == "AGENT":
        metadata["span_kind"] = "agent_call"
        metadata["agent_call"] = name
        metadata["span_roles"] = ["agent_call"]
    else:
        metadata["span_kind"] = "span"
        metadata["span_roles"] = ["span"]
    if langfuse_type == "AGENT":
        metadata["agent_call"] = name
        if "agent_call" not in metadata["span_roles"]:
            metadata["span_roles"].append("agent_call")
    if name == "compile_structural_rules":
        metadata["span_kind"] = "tool_call"
        metadata["tool_name"] = name
        if "tool_call" not in metadata["span_roles"]:
            metadata["span_roles"].append("tool_call")
    return metadata


def _io_payload(value: Any, *, field_name: str) -> dict[str, Any]:
    parsed = _loads_jsonish(value)
    if isinstance(parsed, dict):
        return parsed
    return {field_name: parsed}


def _loads_jsonish(value: Any) -> Any:
    if not isinstance(value, str):
        return value if value is not None else {}
    stripped = value.strip()
    if not stripped:
        return {}
    try:
        return json.loads(stripped)
    except json.JSONDecodeError:
        return stripped


def _langsmith_run_type(observation: dict[str, Any]) -> str:
    langfuse_type = str(observation.get("type") or "").upper()
    return LANGFUSE_TYPE_TO_LANGSMITH_RUN_TYPE.get(langfuse_type, "chain")


def _error_for_observation(observation: dict[str, Any]) -> str | None:
    level = str(observation.get("level") or "").upper()
    status = _string_or_none(observation.get("statusMessage"))
    if level == "ERROR":
        return status or "Langfuse observation marked ERROR."
    return None


def _root_observation(observations: list[dict[str, Any]]) -> dict[str, Any] | None:
    for observation in observations:
        if not observation.get("parentObservationId"):
            return observation
    return observations[0] if observations else None


def _observation_sort_key(observation: dict[str, Any]) -> tuple[str, str]:
    return (str(observation.get("startTime") or ""), str(observation.get("id") or ""))


def _mapped_time(
    value: Any,
    *,
    root_start: datetime,
    original_root_start: datetime | None,
) -> datetime:
    parsed = _parse_time(value)
    if parsed is None or original_root_start is None:
        return root_start
    offset = parsed - original_root_start
    if offset < timedelta(0):
        offset = timedelta(0)
    return root_start + offset


def _parse_time(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)
    except ValueError:
        return None


def _cloud_time(value: Any) -> datetime | None:
    return _parse_time(value)


def _disable_buffered_run_ingest(client: Client) -> None:
    """Force create_run errors to surface synchronously in this one-shot script."""

    if hasattr(client, "_process_buffered_run_ops"):
        setattr(client, "_process_buffered_run_ops", False)


def _run_metadata(run: Any) -> dict[str, Any]:
    metadata = getattr(run, "metadata", None)
    if isinstance(metadata, dict):
        return metadata
    extra = getattr(run, "extra", None)
    if isinstance(extra, dict) and isinstance(extra.get("metadata"), dict):
        return extra["metadata"]
    return {}


def _string_or_none(value: Any) -> str | None:
    if isinstance(value, str) and value:
        return value
    return None


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="Write the backfill to LangSmith.")
    parser.add_argument(
        "--project-name",
        default=None,
        help="LangSmith project name. Defaults to LANGSMITH_PROJECT or autonomous-robot-codesign.",
    )
    parser.add_argument("--env-path", default=".env", help="Path to the repo .env file.")
    parser.add_argument("--limit", type=int, default=None, help="Maximum imported roots to scan.")
    parser.add_argument(
        "--update-roots",
        action="store_true",
        help=(
            "Also patch imported root runs. Existing LangSmith imported roots may reject "
            "this with 'payloads already received', so child-span backfill leaves roots "
            "unchanged by default."
        ),
    )
    parser.add_argument(
        "--update-children",
        action="store_true",
        help=(
            "Patch existing child runs. Existing LangSmith runs can reject payload "
            "updates after ingest, so the default is to leave already-created "
            "child spans untouched."
        ),
    )
    parser.add_argument(
        "--langfuse-trace-id",
        default=None,
        help="Only backfill the imported root for this Langfuse trace ID.",
    )
    return parser.parse_args()


if __name__ == "__main__":
    main()
