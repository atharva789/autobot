"""Tests for the research experimentation layer core modules."""

from __future__ import annotations

import sqlite3
import tempfile
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pytest

from packages.pipeline.ir.design_ir import (
    ActuatorSlot,
    Collision,
    Geometry,
    Inertial,
    JointIR,
    JointLimits,
    JointType,
    LinkIR,
    RobotDesignIR,
    Vector3,
    Visual,
)
from packages.research.benchmark.diversity import (
    link_count_entropy,
    mean_pairwise_distance,
    pairwise_structural_distance,
    shannon_entropy,
)
from packages.research.benchmark.harness import evaluate_designs, evaluate_single
from packages.research.benchmark.metrics import MetricsReport
from packages.research.experiment.types import (
    Experiment,
    ExperimentRun,
    ReproEnvelope,
    TestPrompt,
)
from packages.research.experiment.comparison import (
    compare_runs,
    compare_runs_by_prompt_label,
    format_grouped_comparison_tables,
)
from packages.research.experiment.task_registry import TaskRegistry
from packages.research.prompts.registry import PromptRegistry
from packages.research.storage.store import SQLiteStore
from packages.research.strategy.llm_materializer import LLMIRMaterializer
from packages.research.strategy.protocol import GenerationStrategy, StrategyConfig
from packages.research.strategy.registry import list_strategies, register_strategy


def _make_link(name: str, mass: float = 1.0) -> LinkIR:
    geom = Geometry(type="box", size=(0.1, 0.1, 0.1))
    return LinkIR(
        name=name,
        inertial=Inertial(mass=mass),
        visual=Visual(geometry=geom),
        collision=Collision(geometry=geom),
    )


def _make_joint(name: str, parent: str, child: str) -> JointIR:
    return JointIR(
        name=name,
        joint_type=JointType.REVOLUTE,
        parent_link=parent,
        child_link=child,
        axis=Vector3(1.0, 0.0, 0.0),
        limits=JointLimits(),
        actuator=ActuatorSlot(actuator_type="position", max_torque=10.0),
    )


def _make_ir(name: str = "test", n_links: int = 2) -> RobotDesignIR:
    links = [_make_link(f"link_{i}") for i in range(n_links)]
    joints = [
        _make_joint(f"joint_{i}", f"link_{i}", f"link_{i+1}")
        for i in range(n_links - 1)
    ]
    return RobotDesignIR(name=name, links=links, joints=joints)


class TestStrategyProtocol:
    def test_strategy_config_is_frozen(self) -> None:
        config = StrategyConfig(seed=42, model_id="test")
        with pytest.raises(AttributeError):
            config.seed = 99  # type: ignore[misc]

    def test_protocol_check(self) -> None:
        class FakeStrategy:
            @property
            def name(self) -> str:
                return "fake"

            @property
            def version(self) -> str:
                return "0.1"

            def generate(self, prompt: str, config: StrategyConfig) -> list[RobotDesignIR]:
                return []

        assert isinstance(FakeStrategy(), GenerationStrategy)


class TestPromptRegistry:
    def test_load_template(self) -> None:
        registry = PromptRegistry()
        tpl = registry.load("v1_materializer")
        assert tpl.name == "v1_materializer"
        assert tpl.version == "1.0.0"
        assert len(tpl.sha256) == 64
        assert "node_name" in tpl.variables

    def test_render_template(self) -> None:
        registry = PromptRegistry()
        rendered = registry.render(
            "v1_materializer",
            user_prompt="test",
            node_name="TORSO",
            node_role="root",
            neighbors="HEAD, LEG",
            tree_depth="0",
            morphology_family="quadruped",
        )
        assert "TORSO" in rendered
        assert "quadruped" in rendered

    def test_list_templates(self) -> None:
        registry = PromptRegistry()
        templates = registry.list_templates()
        assert "v1_materializer" in templates
        assert "v1_normalizer" in templates

    def test_missing_template_raises(self) -> None:
        registry = PromptRegistry()
        with pytest.raises(FileNotFoundError):
            registry.load("nonexistent")

    def test_all_hashes_cached(self) -> None:
        registry = PromptRegistry()
        registry.load("v1_materializer")
        registry.load("v1_normalizer")
        hashes = registry.all_hashes()
        assert len(hashes) == 2
        assert all(len(h) == 64 for h in hashes.values())


class TestDiversity:
    def test_shannon_entropy_uniform(self) -> None:
        counts = Counter({1: 5, 2: 5, 3: 5, 4: 5})
        assert shannon_entropy(counts) == pytest.approx(2.0)

    def test_shannon_entropy_single(self) -> None:
        assert shannon_entropy(Counter({1: 10})) == 0.0

    def test_link_count_entropy(self) -> None:
        designs = [_make_ir("a", 2), _make_ir("b", 3), _make_ir("c", 2)]
        entropy = link_count_entropy(designs)
        assert entropy > 0

    def test_pairwise_distance_identical(self) -> None:
        ir = _make_ir("same", 3)
        assert pairwise_structural_distance(ir, ir) == 0.0

    def test_pairwise_distance_different(self) -> None:
        a = _make_ir("a", 2)
        b = _make_ir("b", 5)
        dist = pairwise_structural_distance(a, b)
        assert dist > 0

    def test_mean_pairwise_single(self) -> None:
        assert mean_pairwise_distance([_make_ir()]) == 0.0


class TestBenchmarkHarness:
    def test_evaluate_single_valid(self) -> None:
        ir = _make_ir("test", 2)
        m = evaluate_single(ir)
        assert m.ir_valid
        assert m.link_count == 2
        assert m.joint_count == 1

    def test_evaluate_single_invalid_ir(self) -> None:
        ir = RobotDesignIR(
            name="broken",
            links=[_make_link("a")],
            joints=[_make_joint("j", "a", "missing")],
        )
        m = evaluate_single(ir)
        assert not m.ir_valid
        assert len(m.ir_errors) > 0

    def test_evaluate_designs_empty(self) -> None:
        report = evaluate_designs([])
        assert report.total_designs == 0

    def test_evaluate_designs_batch(self) -> None:
        designs = [_make_ir(f"d{i}", i + 2) for i in range(3)]
        report = evaluate_designs(designs, wall_time_seconds=1.5)
        assert report.total_designs == 3
        assert report.wall_time_seconds == 1.5


class TestSQLiteStore:
    def test_experiment_crud(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = SQLiteStore(db_path=Path(tmp) / "test.db")
            exp = Experiment(
                experiment_id="e1",
                name="test-exp",
                description="desc",
            )
            store.save_experiment(exp)

            loaded = store.load_experiment("e1")
            assert loaded is not None
            assert loaded.name == "test-exp"

            by_name = store.find_experiment_by_name("test-exp")
            assert by_name is not None
            assert by_name.experiment_id == "e1"

            all_exps = store.list_experiments()
            assert len(all_exps) == 1
            store.close()

    def test_task_registry_registers_and_lists_test_prompts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = SQLiteStore(db_path=Path(tmp) / "test.db")
            registry = TaskRegistry(store=store)
            prompts: list[TestPrompt] = [
                {
                    "prompt": "quadruped robot with four legs",
                    "label": "morphlogy-provided",
                },
                {
                    "prompt": "robot that should infer one morphology",
                    "label": "infer-morphology-single",
                },
            ]

            registered = registry.register_many(prompts)

            assert [item["prompt"] for item in registered] == [
                item["prompt"] for item in prompts
            ]
            assert registered[0]["expected_robo_grammar"] == {
                "S": ["BODY", "LEG_PAIR", "LEG_PAIR"]
            }
            assert registry.list() == registered
            assert registry.list(label="morphlogy-provided") == [registered[0]]
            store.close()

    def test_task_registry_does_not_add_duplicate_prompt_text(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = SQLiteStore(db_path=Path(tmp) / "test.db")
            registry = TaskRegistry(store=store)

            first = registry.register(
                "robot that climbs stairs",
                "morphlogy-provided",
            )
            second = registry.register(
                "robot that climbs stairs",
                "infer-morphology-single",
            )

            assert first["prompt"] == "robot that climbs stairs"
            assert first["label"] == "morphlogy-provided"
            assert first["expected_robo_grammar"]["S"] == [
                "BODY",
                "CLIMBING_LEG_PAIR",
                "CLIMBING_LEG_PAIR",
                "STABILIZER",
            ]
            assert second == first
            assert registry.list() == [first]
            store.close()

    def test_task_registry_infers_expected_robo_grammar(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = SQLiteStore(db_path=Path(tmp) / "test.db")
            registry = TaskRegistry(store=store)

            registered = registry.register(
                "quadruped robot that can climb stairs",
                "morphlogy-provided",
            )

            assert registered["expected_robo_grammar"]["S"] == [
                "BODY",
                "CLIMBING_LEG_PAIR",
                "CLIMBING_LEG_PAIR",
                "TAIL",
            ]
            assert registry.list() == [registered]
            store.close()

    def test_task_registry_clears_existing_duplicate_prompt_text(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "test.db"
            legacy_conn = sqlite3.connect(str(db_path))
            legacy_conn.execute(
                """CREATE TABLE test_prompts (
                prompt_id TEXT PRIMARY KEY,
                prompt TEXT NOT NULL,
                label TEXT NOT NULL,
                created_at TEXT NOT NULL
                )"""
            )
            legacy_conn.executemany(
                """INSERT INTO test_prompts (prompt_id, prompt, label, created_at)
                VALUES (?, ?, ?, ?)""",
                [
                    (
                        "duplicate-1",
                        "duplicate prompt",
                        "morphlogy-provided",
                        "2026-01-01T00:00:00+00:00",
                    ),
                    (
                        "duplicate-2",
                        "duplicate prompt",
                        "open-ended",
                        "2026-01-02T00:00:00+00:00",
                    ),
                ],
            )
            legacy_conn.commit()
            legacy_conn.close()

            reopened = SQLiteStore(db_path=db_path)
            registry = TaskRegistry(store=reopened)

            assert registry.list() == [
                {
                    "prompt": "duplicate prompt",
                    "label": "morphlogy-provided",
                    "expected_robo_grammar": {"S": ["BODY"]},
                }
            ]
            reopened.close()

    def test_designs_persistence(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = SQLiteStore(db_path=Path(tmp) / "test.db")
            exp = Experiment(experiment_id="e2", name="design-test")
            store.save_experiment(exp)

            designs = [_make_ir(f"robot_{i}", 3) for i in range(3)]
            store.save_designs("run-1", designs)
            store.close()

    def test_metrics_persistence(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = SQLiteStore(db_path=Path(tmp) / "test.db")
            report = MetricsReport(
                total_designs=2,
                compile_rate=0.5,
                mean_screening_score=0.75,
            )
            store.save_metrics("run-2", report)

            loaded = store.load_run_metrics("run-2")
            assert loaded is not None
            assert loaded.total_designs == 2
            assert loaded.compile_rate == 0.5
            store.close()


class TestRunDebug:
    def test_robo_grammar_eval_counts_extra_leg_pairs(self) -> None:
        from packages.research.experiment.run_debug import evaluate_robo_grammar

        expected = {
            "S": [
                "BODY",
                "CLIMBING_LEG_PAIR",
                "CLIMBING_LEG_PAIR",
                "TAIL",
            ]
        }
        observed = {
            "S": [
                "BODY",
                "CLIMBING_LEG_PAIR",
                "CLIMBING_LEG_PAIR",
                "CLIMBING_LEG_PAIR",
                "CLIMBING_LEG_PAIR",
                "TAIL",
            ]
        }

        result = evaluate_robo_grammar(expected, observed)

        assert result.confusion.true_positives == 4
        assert result.confusion.false_positives == 2
        assert result.confusion.false_negatives == 0
        assert result.node_failures == [
            {
                "pipeline_node": "build_structural_rules",
                "grammar_node": "CLIMBING_LEG_PAIR",
                "kind": "false_positive",
                "expected_count": 2,
                "observed_count": 4,
                "message": "build_structural_rules produced 2 extra CLIMBING_LEG_PAIR edge(s).",
            }
        ]

    def test_run_debug_reads_trace_and_flags_evaluator_miss(self) -> None:
        from packages.research.experiment.run_debug import RunDebugAPI

        class FakeTraceReader:
            def fetch_trace(self, trace_id: str) -> dict[str, Any]:
                assert trace_id == "trace-1"
                return {
                    "trace_id": trace_id,
                    "observations": [
                        {
                            "name": "build_structural_rules",
                            "type": "AGENT",
                            "output": {
                                "structural_rules": {
                                    "S": [
                                        "BODY",
                                        "CLIMBING_LEG_PAIR",
                                        "CLIMBING_LEG_PAIR",
                                        "CLIMBING_LEG_PAIR",
                                        "CLIMBING_LEG_PAIR",
                                        "TAIL",
                                    ]
                                }
                            },
                        },
                        {
                            "name": "evaluate_rules",
                            "type": "EVALUATOR",
                            "output": {
                                "criteria": [
                                    {
                                        "description": "Rules match the quadruped stair-climbing oracle.",
                                        "isSuccessful": True,
                                        "critiques": [],
                                    }
                                ]
                            },
                        },
                    ],
                }

        with tempfile.TemporaryDirectory() as tmp:
            store = SQLiteStore(db_path=Path(tmp) / "test.db")
            run = ExperimentRun(
                run_id="run-1",
                experiment_id="exp-1",
                strategy_name="grammar",
                prompt="quadruped robot that can climb stairs",
                config=StrategyConfig(seed=1, model_id="test", max_candidates=1),
                repro=ReproEnvelope(
                    seed=1,
                    model_id="test",
                    prompt_hash="hash",
                    strategy_name="grammar",
                    strategy_version="1",
                ),
                started_at=datetime.now(timezone.utc),
                finished_at=datetime.now(timezone.utc),
                prompt_label="morphlogy-provided",
                langfuse_trace_id="trace-1",
            )
            store.save_experiment(Experiment(experiment_id="exp-1", name="debug-exp"))
            store.save_test_prompt(
                {
                    "prompt": run.prompt,
                    "label": "morphlogy-provided",
                    "expected_robo_grammar": {
                        "S": [
                            "BODY",
                            "CLIMBING_LEG_PAIR",
                            "CLIMBING_LEG_PAIR",
                            "TAIL",
                        ]
                    },
                }
            )
            store.save_run(run)

            debugged = RunDebugAPI(store=store, trace_reader=FakeTraceReader()).debug_run(
                run.run_id
            )

            assert debugged.debug is not None
            assert debugged.debug.confusion.false_positives == 2
            assert any(
                failure["pipeline_node"] == "evaluate_rules"
                and failure["kind"] == "false_negative"
                for failure in debugged.debug.node_failures
            )
            loaded = store.load_run(run.run_id)
            assert loaded is not None
            assert loaded.debug == debugged.debug
            store.close()

    def test_run_debug_can_debug_cloud_trace_without_prompt_arg(self) -> None:
        from packages.research.experiment.run_debug import RunDebugAPI

        class FakeTraceReader:
            def fetch_trace(self, trace_id: str) -> dict[str, Any]:
                assert trace_id == "cloud-trace-1"
                return {
                    "trace_id": trace_id,
                    "observations": [
                        {
                            "name": "robogrammar.structural_rule_graph",
                            "type": "AGENT",
                            "input": {
                                "prompt": "quadruped robot that can climb stairs",
                                "population": 3,
                            },
                        },
                        {
                            "name": "build_structural_rules",
                            "type": "AGENT",
                            "output": {
                                "structural_rules": {
                                    "S": ["BODY", "CLIMBING_LEG_PAIR", "TAIL"]
                                }
                            },
                        }
                    ],
                }

        report = RunDebugAPI(trace_reader=FakeTraceReader()).debug_trace(
            "cloud-trace-1",
        )

        assert report.langsmith_trace_id == "cloud-trace-1"
        assert report.expected_robo_grammar == {
            "S": ["BODY", "CLIMBING_LEG_PAIR", "CLIMBING_LEG_PAIR", "TAIL"]
        }
        assert report.confusion.false_negatives == 1

    def test_run_debug_defaults_to_langsmith_reader(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from packages.research.experiment.run_debug import (
            LangSmithTraceReader,
            RunDebugAPI,
        )

        def fake_init(self, **_kwargs: Any) -> None:
            self.project_name = "test-project"
            self.client = object()

        monkeypatch.setattr(LangSmithTraceReader, "__init__", fake_init)

        with tempfile.TemporaryDirectory() as tmp:
            api = RunDebugAPI(store=SQLiteStore(db_path=Path(tmp) / "test.db"))

        assert isinstance(api.trace_reader, LangSmithTraceReader)

    def test_run_debug_can_opt_into_langfuse_reader(self) -> None:
        from packages.research.experiment.run_debug import (
            LangfuseTraceReader,
            RunDebugAPI,
        )

        with tempfile.TemporaryDirectory() as tmp:
            api = RunDebugAPI(
                store=SQLiteStore(db_path=Path(tmp) / "test.db"),
                use_langfuse=True,
            )

        assert isinstance(api.trace_reader, LangfuseTraceReader)

    def test_run_debug_extracts_prompt_from_prefixed_observation_input(self) -> None:
        from packages.research.experiment.run_debug import extract_prompt_from_trace

        prompt = extract_prompt_from_trace(
            {
                "observations": [
                    {
                        "name": "build_structural_rules",
                        "input": (
                            "Generate compile-safe structural_rules.\n\n"
                            '{"prompt": "robot family for mixed terrain search and rescue"}'
                        ),
                    }
                ]
            }
        )

        assert prompt == "robot family for mixed terrain search and rescue"

    def test_run_debug_extracts_prompt_from_chat_task_message(self) -> None:
        from packages.research.experiment.run_debug import extract_prompt_from_trace

        prompt = extract_prompt_from_trace(
            {
                "observations": [
                    {
                        "name": "LangGraph",
                        "input": {
                            "messages": [
                                {
                                    "type": "human",
                                    "content": "Task: Design a small quadruped robot for stair climbing.",
                                }
                            ]
                        },
                    }
                ]
            }
        )

        assert prompt == "Design a small quadruped robot for stair climbing."

    def test_langsmith_reader_fetch_trace_caps_query_limit(self) -> None:
        from packages.research.experiment.run_debug import LangSmithTraceReader

        calls: list[dict[str, Any]] = []

        class FakeClient:
            def list_runs(self, **kwargs: Any) -> list[Any]:
                calls.append(kwargs)
                return []

        reader = object.__new__(LangSmithTraceReader)
        reader.project_name = "test-project"
        reader.client = FakeClient()

        trace = reader.fetch_trace("trace-1")

        assert trace["observations"] == []
        assert calls[0]["limit"] == 100

    def test_run_debug_extracts_nested_root_structural_rules(self) -> None:
        from packages.research.experiment.run_debug import extract_robo_grammar_from_trace

        rules = extract_robo_grammar_from_trace(
            {
                "observations": [
                    {
                        "name": "robogrammar.structural_rule_graph",
                        "output": {
                            "output": {
                                "structural_rules": {
                                    "S": ["BODY", "LEG_PAIR", "LEG_PAIR"]
                                }
                            }
                        },
                    }
                ]
            }
        )

        assert rules == {"S": ["BODY", "LEG_PAIR", "LEG_PAIR"]}

    def test_run_debug_extracts_structural_rules_from_message_content(self) -> None:
        from packages.research.experiment.run_debug import extract_robo_grammar_from_trace

        rules = extract_robo_grammar_from_trace(
            {
                "observations": [
                    {
                        "name": "LangGraph",
                        "output": {
                            "messages": [
                                {
                                    "type": "ai",
                                    "content": (
                                        "```json\n"
                                        '{"structural_rules": {"S": ["BODY", "LEG_PAIR"]}}\n'
                                        "```"
                                    ),
                                }
                            ]
                        },
                    }
                ]
            }
        )

        assert rules == {"S": ["BODY", "LEG_PAIR"]}

    def test_run_debug_can_persist_cloud_trace_report(self) -> None:
        from packages.research.experiment.run_debug import RunDebugAPI

        class FakeTraceReader:
            def fetch_trace(self, _trace_id: str) -> dict[str, Any]:
                return {
                    "observations": [
                        {
                            "name": "build_structural_rules",
                            "output": {
                                "structural_rules": {
                                    "S": [
                                        "BODY",
                                        "CLIMBING_LEG_PAIR",
                                        "CLIMBING_LEG_PAIR",
                                        "TAIL",
                                    ]
                                }
                            },
                        }
                    ]
                }

        with tempfile.TemporaryDirectory() as tmp:
            store = SQLiteStore(db_path=Path(tmp) / "test.db")
            api = RunDebugAPI(store=store, trace_reader=FakeTraceReader())

            report = api.debug_trace(
                "cloud-trace-2",
                prompt="quadruped robot that can climb stairs",
                prompt_label="morphlogy-provided",
                persist=True,
            )

            loaded = store.load_run("cloud-trace-2")
            assert loaded is not None
            assert loaded.debug == report
            store.close()

    def test_run_debug_handles_missing_codex_cli(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from packages.research.experiment.run_debug import RunDebugAPI
        import packages.research.experiment.run_debug as run_debug_module

        class FakeTraceReader:
            def fetch_trace(self, _trace_id: str) -> dict[str, Any]:
                return {
                    "observations": [
                        {
                            "name": "robogrammar.structural_rule_graph",
                            "input": {"prompt": "quadruped robot that can climb stairs"},
                        },
                        {
                            "name": "build_structural_rules",
                            "output": {
                                "structural_rules": {
                                    "S": [
                                        "BODY",
                                        "CLIMBING_LEG_PAIR",
                                        "CLIMBING_LEG_PAIR",
                                        "TAIL",
                                    ]
                                }
                            },
                        },
                    ]
                }

        def raise_missing_cli(*_args: Any, **_kwargs: Any) -> None:
            raise FileNotFoundError("No such file or directory: 'codex'")

        monkeypatch.setattr(run_debug_module.subprocess, "run", raise_missing_cli)

        report = RunDebugAPI(trace_reader=FakeTraceReader()).debug_trace(
            "trace-without-codex",
            use_codex=True,
        )

        assert report.codex_analysis is not None
        assert report.codex_analysis["summary"] == "Codex trace analysis unavailable."
        assert "codex" in report.codex_analysis["failure_hypotheses"][0]

    def test_run_debug_uses_codex_cli_env_override(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        from packages.research.experiment.run_debug import RunDebugAPI
        import packages.research.experiment.run_debug as run_debug_module

        class FakeTraceReader:
            def fetch_trace(self, _trace_id: str) -> dict[str, Any]:
                return {
                    "observations": [
                        {
                            "name": "robogrammar.structural_rule_graph",
                            "input": {"prompt": "quadruped robot that can climb stairs"},
                        },
                        {
                            "name": "build_structural_rules",
                            "output": {
                                "structural_rules": {
                                    "S": [
                                        "BODY",
                                        "CLIMBING_LEG_PAIR",
                                        "CLIMBING_LEG_PAIR",
                                        "TAIL",
                                    ]
                                }
                            },
                        },
                    ]
                }

        calls: list[list[str]] = []

        class FakeCompletedProcess:
            returncode = 0
            stdout = '{"summary":"ok","failure_hypotheses":[],"node_failure_notes":[],"proxy_quality_notes":[]}\n'
            stderr = ""

        def fake_run(cmd: list[str], **_kwargs: Any) -> FakeCompletedProcess:
            calls.append(cmd)
            schema_path = Path(cmd[cmd.index("--output-schema") + 1])
            schema = json.loads(schema_path.read_text())
            node_note_items = schema["properties"]["node_failure_notes"]["items"]
            assert node_note_items["additionalProperties"] is False
            assert node_note_items["required"]
            return FakeCompletedProcess()

        monkeypatch.setenv("CODEX_CLI", "/tmp/custom-codex")
        monkeypatch.setattr(run_debug_module.subprocess, "run", fake_run)

        report = RunDebugAPI(trace_reader=FakeTraceReader()).debug_trace(
            "trace-with-codex-env",
            use_codex=True,
        )

        assert any(call[0] == "/tmp/custom-codex" for call in calls)
        assert report.codex_analysis is not None
        assert report.codex_analysis["summary"] == "ok"

    def test_langfuse_reader_loads_base_url_from_dotenv(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        from packages.research.experiment.run_debug import LangfuseTraceReader

        monkeypatch.delenv("LANGFUSE_PUBLIC_KEY", raising=False)
        monkeypatch.delenv("LANGFUSE_SECRET_KEY", raising=False)
        monkeypatch.delenv("LANGFUSE_HOST", raising=False)
        monkeypatch.delenv("LANGFUSE_BASE_URL", raising=False)

        with tempfile.TemporaryDirectory() as tmp:
            env_path = Path(tmp) / ".env"
            env_path.write_text(
                "\n".join(
                    [
                        "LANGFUSE_PUBLIC_KEY=pk-test",
                        "LANGFUSE_SECRET_KEY=sk-test",
                        "LANGFUSE_BASE_URL=https://us.cloud.langfuse.com",
                    ]
                )
            )

            reader = LangfuseTraceReader(env_path=env_path)

        assert reader.public_key == "pk-test"
        assert reader.secret_key == "sk-test"
        assert reader.host == "https://us.cloud.langfuse.com"

    def test_langfuse_reader_lists_run_refs_newest_first(self) -> None:
        from packages.research.experiment.run_debug import LangfuseTraceReader

        class FakeReader(LangfuseTraceReader):
            def __init__(self) -> None:
                super().__init__(
                    host="https://langfuse.test",
                    public_key="pk-test",
                    secret_key="sk-test",
                )
                self.urls: list[str] = []

            def _get_json(self, url: str) -> dict[str, Any]:
                self.urls.append(url)
                if "cursor=page-2" in url:
                    return {
                        "data": [
                            {
                                "id": "obs-4",
                                "traceId": "trace-c",
                                "startTime": "2026-05-21T00:00:01.000Z",
                                "name": "robogrammar.structural_rule_graph",
                            }
                        ],
                        "meta": {},
                    }
                return {
                    "data": [
                        {
                            "id": "obs-1",
                            "traceId": "trace-a",
                            "startTime": "2026-05-21T00:00:03.000Z",
                            "name": "resolve_grammar_node_names",
                        },
                        {
                            "id": "obs-2",
                            "traceId": "trace-a",
                            "startTime": "2026-05-21T00:00:02.000Z",
                            "name": "build_structural_rules",
                        },
                        {
                            "id": "obs-3",
                            "traceId": "trace-b",
                            "startTime": "2026-05-21T00:00:02.500Z",
                            "name": "robogrammar.structural_rule_graph",
                        },
                    ],
                    "meta": {"cursor": "page-2"},
                }

        refs = FakeReader().list_run_refs(limit=3, page_size=2)

        assert [ref.trace_id for ref in refs] == ["trace-a", "trace-b", "trace-c"]
        assert refs[0].last_observation_at == "2026-05-21T00:00:03.000Z"
        assert refs[0].latest_observation_name == "resolve_grammar_node_names"

    def test_run_debug_api_exposes_langfuse_run_id_shortcuts(self) -> None:
        from packages.research.experiment.run_debug import RunDebugAPI
        from packages.research.experiment.types import LangfuseRunRef

        class FakeTraceReader:
            def fetch_trace(self, _trace_id: str) -> dict[str, Any]:
                return {"observations": []}

            def list_run_refs(
                self,
                *,
                limit: int | None = 20,
                **_kwargs: Any,
            ) -> list[LangfuseRunRef]:
                refs = [
                    LangfuseRunRef(trace_id="trace-a", last_observation_at="3"),
                    LangfuseRunRef(trace_id="trace-b", last_observation_at="2"),
                    LangfuseRunRef(trace_id="trace-c", last_observation_at="1"),
                ]
                return refs if limit is None else refs[:limit]

        api = RunDebugAPI(trace_reader=FakeTraceReader())

        assert api.last_run_id() == "trace-a"
        assert api.last_k_run_ids(2) == ["trace-a", "trace-b"]
        assert api.all_run_ids() == ["trace-a", "trace-b", "trace-c"]

    def test_run_debug_notebook_uses_current_batch_api(self) -> None:
        notebook_path = Path("packages/research/notebooks/run_debug_api.ipynb")
        notebook = json.loads(notebook_path.read_text())
        source = "\n".join(
            "".join(cell.get("source", [])) for cell in notebook["cells"]
        )

        assert "last_k_runs(" not in source
        assert "last_k_run_ids(3)" in source
        assert "batch_debug_trace(batch_trace_ids)" in source

    def test_batch_debug_trace_uses_one_codex_batch_analysis(self) -> None:
        from packages.research.experiment.run_debug import RunDebugAPI

        class FakeTraceReader:
            def fetch_trace(self, trace_id: str) -> dict[str, Any]:
                prompts = {
                    "trace-a": "quadruped robot that can climb stairs",
                    "trace-b": "robot for moving fragile objects across clutter",
                }
                rules = {
                    "trace-a": {"S": ["BODY", "CLIMBING_LEG_PAIR", "TAIL"]},
                    "trace-b": {"S": ["BODY_CHAIN"]},
                }
                return {
                    "trace_id": trace_id,
                    "observations": [
                        {
                            "name": "robogrammar.structural_rule_graph",
                            "input": {"prompt": prompts[trace_id]},
                        },
                        {
                            "name": "build_structural_rules",
                            "output": {"structural_rules": rules[trace_id]},
                        },
                    ],
                }

        class FakeBatchAnalyzer:
            def __init__(self) -> None:
                self.calls: list[list[str]] = []

            def analyze_batch(self, *, reports: list[Any], traces: list[dict[str, Any]]) -> dict[str, Any]:
                self.calls.append([report.run_id for report in reports])
                return {
                    "summary": f"batch saw {len(reports)} runs and {len(traces)} traces",
                    "cross_run_patterns": ["builder misses expected nodes"],
                    "node_failure_patterns": [],
                    "proxy_quality_patterns": [],
                    "recommended_next_actions": [],
                }

        analyzer = FakeBatchAnalyzer()

        batch = RunDebugAPI(
            trace_reader=FakeTraceReader(),
            codex_analyzer=analyzer,  # type: ignore[arg-type]
        ).batch_debug_trace(["trace-a", "trace-b"])

        assert [report.run_id for report in batch.reports] == ["trace-a", "trace-b"]
        assert analyzer.calls == [["trace-a", "trace-b"]]
        assert batch.codex_batch_analysis["summary"] == "batch saw 2 runs and 2 traces"
        assert batch.summary["runs"] == 2

    def test_batch_debug_trace_prints_vertically(self) -> None:
        from packages.research.experiment.types import (
            BatchDebugReport,
            ConfusionMatrix,
            RunDebugReport,
        )

        batch = BatchDebugReport(
            trace_ids=("trace-a",),
            reports=(
                RunDebugReport(
                    run_id="trace-a",
                    strategy_name="grammar",
                    langfuse_trace_id="trace-a",
                    expected_robo_grammar={"S": ["BODY"]},
                    observed_robo_grammar={"S": ["BODY", "TAIL"]},
                    confusion=ConfusionMatrix(true_positives=1, false_positives=1),
                ),
            ),
            summary={"runs": 1, "failed_runs": 1},
            codex_batch_analysis={"summary": "one systematic builder issue"},
        )

        rendered = str(batch)

        assert rendered.startswith("BatchDebugReport")
        assert "\n  trace_ids: 1" in rendered
        assert "\n  summary:" in rendered
        assert "\n  codex_batch_analysis:" in rendered

    def test_run_debug_report_prints_vertically(self) -> None:
        from packages.research.experiment.types import ConfusionMatrix, RunDebugReport

        report = RunDebugReport(
            run_id="run-1",
            strategy_name="grammar",
            langfuse_trace_id="trace-1",
            expected_robo_grammar={"S": ["BODY", "LEG_PAIR"]},
            observed_robo_grammar={"S": ["BODY", "LEG_PAIR", "TAIL"]},
            confusion=ConfusionMatrix(
                true_positives=2,
                false_positives=1,
                false_negatives=0,
            ),
            node_failures=[
                {
                    "pipeline_node": "build_structural_rules",
                    "kind": "false_positive",
                    "grammar_node": "TAIL",
                    "message": "extra tail",
                }
            ],
            proxy_checks=[
                {
                    "pipeline_node": "evaluate_rules",
                    "description": "payload proxy",
                    "covers_expected_structure": False,
                }
            ],
            observation_count=3,
            codex_analysis={"summary": "builder over-expanded the structure"},
        )

        rendered = str(report)

        assert rendered.startswith("RunDebugReport")
        assert "\n  run_id: run-1" in rendered
        assert "\n  confusion:" in rendered
        assert "\n  expected_robo_grammar:" in rendered
        assert "\n  node_failures" in rendered
        assert "RunDebugReport(run_id=" not in repr(report)

    def test_run_debug_report_has_ipython_pretty_repr(self) -> None:
        from packages.research.experiment.types import ConfusionMatrix, RunDebugReport

        class PrettyPrinter:
            def __init__(self) -> None:
                self.value = ""

            def text(self, value: str) -> None:
                self.value = value

        report = RunDebugReport(
            run_id="run-1",
            strategy_name="grammar",
            langfuse_trace_id=None,
            expected_robo_grammar={},
            observed_robo_grammar={},
            confusion=ConfusionMatrix(),
        )
        printer = PrettyPrinter()

        report._repr_pretty_(printer, False)

        assert "\n  run_id: run-1" in printer.value


class TestLLMMaterializer:
    def test_fallback_produces_valid_ir(self) -> None:
        materializer = LLMIRMaterializer()
        config = StrategyConfig(seed=42, model_id="test")
        raw = {
            "structural_rules": {
                "S": ["BODY"],
                "BODY": ["HEAD", "LEG"],
            },
            "spec": {"target_morphology": "biped"},
        }
        designs = materializer.materialize(raw, "test prompt", config)
        assert len(designs) == 1
        ir = designs[0]
        assert len(ir.links) == 4
        assert len(ir.joints) == 3
        assert ir.validate() == []

    def test_different_seeds_produce_different_fallback(self) -> None:
        materializer = LLMIRMaterializer()
        raw = {
            "structural_rules": {"S": ["BODY"], "BODY": ["HEAD", "LEG"]},
            "spec": {"target_morphology": "biped"},
        }
        designs_a = materializer.materialize(
            raw, "test", StrategyConfig(seed=1, model_id="test")
        )
        designs_b = materializer.materialize(
            raw, "test", StrategyConfig(seed=99, model_id="test")
        )
        assert len(designs_a) == 1 and len(designs_b) == 1
        link_masses_a = tuple(link.inertial.mass for link in designs_a[0].links)
        link_masses_b = tuple(link.inertial.mass for link in designs_b[0].links)
        assert link_masses_a != link_masses_b

    def test_empty_rules_returns_empty(self) -> None:
        materializer = LLMIRMaterializer()
        config = StrategyConfig(seed=1, model_id="test")
        designs = materializer.materialize(
            {"structural_rules": {}}, "test", config
        )
        assert designs == []


class TestRegistry:
    def test_list_includes_grammar(self) -> None:
        assert "grammar" in list_strategies()

    def test_register_custom_strategy(self) -> None:
        class Custom:
            @property
            def name(self) -> str:
                return "custom"

            @property
            def version(self) -> str:
                return "0.1"

            def generate(self, prompt: str, config: StrategyConfig) -> list[RobotDesignIR]:
                return []

        register_strategy("custom", Custom)
        assert "custom" in list_strategies()


class TestPromptAgents:
    def test_build_registry_agents_returns_three(self) -> None:
        from packages.research.strategy.prompt_agents import build_registry_agents

        registry = PromptRegistry()
        agents = build_registry_agents(registry, "test-model")
        assert set(agents.keys()) == {
            "normalizer_agent",
            "rule_builder_agent",
            "evaluator_agent",
        }

    def test_normalizer_agent_renders_template(self) -> None:
        from packages.research.strategy.prompt_agents import RegistryNormalizerAgent

        registry = PromptRegistry()
        agent = RegistryNormalizerAgent(registry, "test-model")
        result = agent.invoke("Raw user request: build a quadruped")
        assert result is None

    def test_rule_builder_agent_renders_template(self) -> None:
        from packages.research.strategy.prompt_agents import RegistryRuleBuilderAgent

        registry = PromptRegistry()
        agent = RegistryRuleBuilderAgent(registry, "test-model")
        msg = (
            "Robot query context: biped\n"
            "GrammarNodes vocabulary: A, B\n"
            "Compile-valid few-shot structural-rule examples\nS -> A B"
        )
        result = agent.invoke([msg, "build rules"])
        assert result is None

    def test_evaluator_agent_renders_template(self) -> None:
        from packages.research.strategy.prompt_agents import RegistryEvaluatorAgent

        registry = PromptRegistry()
        agent = RegistryEvaluatorAgent(registry, "test-model")
        result = agent.invoke(["system", "Current state: good"])
        assert result is None

    def test_split_messages_string(self) -> None:
        from packages.research.strategy.prompt_agents import _split_messages

        sys, usr = _split_messages("hello")
        assert sys == "hello"
        assert usr == ""

    def test_split_messages_list(self) -> None:
        from packages.research.strategy.prompt_agents import _split_messages

        sys, usr = _split_messages(["sys", "usr"])
        assert sys == "sys"
        assert usr == "usr"

    def test_extract_after(self) -> None:
        from packages.research.strategy.prompt_agents import _extract_after

        assert _extract_after("foo: bar baz", "foo:") == "bar baz"

    def test_extract_section(self) -> None:
        from packages.research.strategy.prompt_agents import _extract_section

        text = "AAA start BBB end CCC"
        assert _extract_section(text, "start", "end") == "start BBB"


class TestExperimentRunnerIntegration:
    def test_run_with_fake_strategy(self) -> None:
        from packages.research.strategy.registry import register_strategy

        class FakeStrategy:
            @property
            def name(self) -> str:
                return "fake-test"

            @property
            def version(self) -> str:
                return "0.1"

            def generate(
                self, prompt: str, config: StrategyConfig
            ) -> list[RobotDesignIR]:
                return [_make_ir("fake_robot", 3)]

        register_strategy("fake-test", FakeStrategy)

        with tempfile.TemporaryDirectory() as tmp:
            store = SQLiteStore(db_path=Path(tmp) / "test.db")
            from packages.research.experiment.runner import ExperimentRunner

            runner = ExperimentRunner(store=store)
            run = runner.run(
                prompt="test robot",
                strategy_name="fake-test",
                experiment_name="integration-test",
                seed=42,
                model_id="test",
                max_candidates=1,
            )
            assert run.error is None
            assert len(run.designs) == 1
            assert run.designs[0].name == "fake_robot"
            assert run.prompt_label is None
            assert run.metrics_report is not None
            assert run.metrics_report.total_designs == 1

            loaded = store.load_run_metrics(run.run_id)
            assert loaded is not None
            assert loaded.total_designs == 1
            store.close()

    def test_run_suite_persists_prompt_labels(self) -> None:
        from packages.research.strategy.registry import register_strategy

        class SuiteStrategy:
            @property
            def name(self) -> str:
                return "suite-test"

            @property
            def version(self) -> str:
                return "0.1"

            def generate(
                self, prompt: str, config: StrategyConfig
            ) -> list[RobotDesignIR]:
                return [_make_ir(f"suite_robot_{config.seed}", 3)]

        register_strategy("suite-test", SuiteStrategy)

        with tempfile.TemporaryDirectory() as tmp:
            store = SQLiteStore(db_path=Path(tmp) / "test.db")
            from packages.research.experiment.runner import ExperimentRunner

            runner = ExperimentRunner(store=store)
            test_prompts: list[TestPrompt] = [
                {
                    "prompt": "quadruped robot with explicit morphology",
                    "label": "morphlogy-provided",
                },
                {
                    "prompt": "robot for open-ended warehouse work",
                    "label": "open-ended",
                },
            ]

            runs = runner.run_suite(
                test_prompts=test_prompts,
                strategy_names=["suite-test"],
                experiment_name="suite-exp",
                max_candidates=1,
                model_id="test",
            )

            assert [run.prompt_label for run in runs] == [
                "morphlogy-provided",
                "open-ended",
            ]
            exp = store.find_experiment_by_name("suite-exp")
            assert exp is not None
            persisted = store.list_runs(exp.experiment_id)
            assert {run.prompt_label for run in persisted} == {
                "morphlogy-provided",
                "open-ended",
            }
            store.close()

    def test_compare_runs_groups_by_prompt_label(self) -> None:
        from packages.research.strategy.registry import register_strategy

        class GroupStrategy:
            @property
            def name(self) -> str:
                return "group-test"

            @property
            def version(self) -> str:
                return "0.1"

            def generate(
                self, prompt: str, config: StrategyConfig
            ) -> list[RobotDesignIR]:
                return [_make_ir(f"group_robot_{config.seed}", 3)]

        register_strategy("group-test", GroupStrategy)

        with tempfile.TemporaryDirectory() as tmp:
            store = SQLiteStore(db_path=Path(tmp) / "test.db")
            from packages.research.experiment.runner import ExperimentRunner

            runner = ExperimentRunner(store=store)
            runs = runner.run_suite(
                test_prompts=[
                    {
                        "prompt": "single morphology prompt",
                        "label": "infer-morphology-single",
                    },
                    {
                        "prompt": "open ended prompt",
                        "label": "open-ended",
                    },
                ],
                strategy_names=["group-test"],
                experiment_name="group-exp",
                max_candidates=1,
                model_id="test",
            )

            flat_rows = compare_runs(runs, store)
            grouped = compare_runs_by_prompt_label(runs, store)
            table = format_grouped_comparison_tables(grouped)

            assert [row.prompt_label for row in flat_rows] == [
                "infer-morphology-single",
                "open-ended",
            ]
            assert list(grouped) == [
                "infer-morphology-single",
                "open-ended",
            ]
            assert "[infer-morphology-single]" in table
            assert "[open-ended]" in table
            store.close()

    def test_run_captures_strategy_error(self) -> None:
        from packages.research.strategy.registry import register_strategy

        class FailStrategy:
            @property
            def name(self) -> str:
                return "fail-test"

            @property
            def version(self) -> str:
                return "0.1"

            def generate(
                self, prompt: str, config: StrategyConfig
            ) -> list[RobotDesignIR]:
                raise RuntimeError("intentional failure")

        register_strategy("fail-test", FailStrategy)

        with tempfile.TemporaryDirectory() as tmp:
            store = SQLiteStore(db_path=Path(tmp) / "test.db")
            from packages.research.experiment.runner import ExperimentRunner

            runner = ExperimentRunner(store=store)
            run = runner.run(
                prompt="test",
                strategy_name="fail-test",
                experiment_name="fail-exp",
            )
            assert run.error is not None
            assert "intentional failure" in run.error
            assert len(run.designs) == 0
            store.close()


class TestGrammarStrategyWiring:
    def test_generate_passes_registry_agents(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Verify that GrammarStrategy.generate() injects registry agents."""
        from packages.research.strategy import grammar_strategy as gs_mod

        captured_kwargs: dict[str, Any] = {}

        def fake_build(prompt: str, **kwargs: Any) -> dict[str, Any]:
            captured_kwargs.update(kwargs)
            return {
                "structural_rules": {"S": ["BODY"], "BODY": ["HEAD"]},
                "spec": {"target_morphology": "biped"},
            }

        monkeypatch.setattr(gs_mod, "build_structural_rules", fake_build)

        from packages.research.strategy.grammar_strategy import GrammarStrategy

        strategy = GrammarStrategy()
        config = StrategyConfig(seed=1, model_id="test", max_candidates=1)
        strategy.generate("test prompt", config)

        assert "normalizer_agent" in captured_kwargs
        assert "rule_builder_agent" in captured_kwargs
        assert "evaluator_agent" in captured_kwargs

        from packages.research.strategy.prompt_agents import (
            RegistryEvaluatorAgent,
            RegistryNormalizerAgent,
            RegistryRuleBuilderAgent,
        )
        assert isinstance(captured_kwargs["normalizer_agent"], RegistryNormalizerAgent)
        assert isinstance(captured_kwargs["rule_builder_agent"], RegistryRuleBuilderAgent)
        assert isinstance(captured_kwargs["evaluator_agent"], RegistryEvaluatorAgent)


class TestReproEnvelope:
    def test_fingerprint_deterministic(self) -> None:
        env = ReproEnvelope(
            seed=42,
            model_id="gpt-4",
            prompt_hash="abc123",
            strategy_name="grammar",
            strategy_version="1.0",
            git_sha="deadbeef",
        )
        assert env.fingerprint() == env.fingerprint()
        assert len(env.fingerprint()) == 16

    def test_different_seeds_different_fingerprints(self) -> None:
        a = ReproEnvelope(
            seed=42, model_id="m", prompt_hash="p",
            strategy_name="s", strategy_version="1", git_sha="g",
        )
        b = ReproEnvelope(
            seed=99, model_id="m", prompt_hash="p",
            strategy_name="s", strategy_version="1", git_sha="g",
        )
        assert a.fingerprint() != b.fingerprint()
