from __future__ import annotations

from contextlib import contextmanager
from types import SimpleNamespace

import pytest
from pydantic import TypeAdapter

from packages.pipeline import db_connections, grammar_graph
from packages.pipeline.schemas import TaskIntent


ENV_KEYS = [
    "SUPABASE_URL",
    "SUPABASE_SERVICE_KEY",
    "SUPABASE_ANON_KEY",
    "NEXT_PUBLIC_SUPABASE_ANON_KEY",
    "GRAMMAR_SUPABASE_URL",
    "GRAMMAR_SUPABASE_SERVICE_KEY",
    "GRAMMAR_SUPABASE_KEY",
    "GRAMMAR_SUPABASE_PUBLISHABLE_KEY",
    "GRAMMAR_TABLE",
    "GRAMMAR_NODES_TABLE",
    "GRAMMAR_NODE_MEMBERSHIPS_TABLE",
    "STRUCTURAL_RULES_TABLE",
    "GRAMMAR_NODES_LIMIT",
    "STRUCTURAL_RULES_LIMIT",
    "GRAMMAR_ACTIVE_ONLY",
]


@pytest.fixture(autouse=True)
def clear_env(monkeypatch: pytest.MonkeyPatch):
    db_connections.get_supabase_client.cache_clear()
    monkeypatch.setattr(db_connections, "load_dotenv", lambda override=False: None)
    for key in ENV_KEYS:
        monkeypatch.delenv(key, raising=False)
    yield
    db_connections.get_supabase_client.cache_clear()


def test_get_supabase_client_reads_grammar_env(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("GRAMMAR_SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("GRAMMAR_SUPABASE_PUBLISHABLE_KEY", "publishable-key")
    calls: list[tuple[str, str]] = []
    monkeypatch.setattr(
        db_connections,
        "create_client",
        lambda url, key: calls.append((url, key)) or object(),
    )

    db_connections.get_supabase_client()

    assert calls == [("https://example.supabase.co", "publishable-key")]


def test_fetch_grammar_from_db_returns_short_and_long_names(
    monkeypatch: pytest.MonkeyPatch,
):
    fake_client = FakeSupabaseClient(
        [{"short_form_name": "B", "long_name": "Body Link"}]
    )
    monkeypatch.setattr(grammar_graph, "get_supabase_client", lambda: fake_client)

    rows = grammar_graph.fetch_grammar_from_db(
        limit=1,
        active_only=True,
        node_type="terminal",
    )

    assert rows == [("B", "Body Link")]
    assert fake_client.calls == [
        ("table", "GrammarNodes"),
        ("select", "short_form_name,long_name"),
        ("eq", "active", True),
        ("eq", "node_type", "terminal"),
        ("limit", 1),
    ]


def test_fetch_grammar_from_db_filters_family_via_memberships(
    monkeypatch: pytest.MonkeyPatch,
):
    fake_client = FakeSupabaseClient(
        {
            "Grammars": [{"id": "quadruped_spot_like"}],
            "GrammarNodeMemberships": [
                {
                    "grammar_id": "quadruped_spot_like",
                    "short_form_name": "B",
                    "node_type": "terminal",
                },
                {
                    "grammar_id": "bird_biped_winged",
                    "short_form_name": "WING",
                    "node_type": "terminal",
                },
            ],
            "GrammarNodes": [
                {"short_form_name": "B", "long_name": "Body Link"},
                {"short_form_name": "WING", "long_name": "Wing"},
            ],
        }
    )
    monkeypatch.setattr(grammar_graph, "get_supabase_client", lambda: fake_client)

    rows = grammar_graph.fetch_grammar_from_db(
        morphology_family="quadruped",
        node_type="terminal",
    )

    assert rows == [("B", "Body Link")]


def test_fetch_desc_by_node_uses_short_form_id(monkeypatch: pytest.MonkeyPatch):
    fake_client = FakeSupabaseClient(
        [{"description": "Rigid body link component."}]
    )
    monkeypatch.setattr(grammar_graph, "get_supabase_client", lambda: fake_client)

    description = grammar_graph.fetch_desc_by_node("B")

    assert description == "Rigid body link component."
    assert fake_client.calls == [
        ("table", "GrammarNodes"),
        ("select", "description"),
        ("eq", "active", True),
        ("eq", "short_form_name", "B"),
        ("limit", 1),
    ]


def test_fetch_rules_from_db_returns_rule_description_memory(
    monkeypatch: pytest.MonkeyPatch,
):
    fake_client = FakeSupabaseClient(
        [{"rule": "BODY -> B LEG_PAIR", "description": "Attach legs to body."}]
    )
    monkeypatch.setattr(grammar_graph, "get_supabase_client", lambda: fake_client)

    rules = grammar_graph.fetch_rules_from_db(
        morphology_family="quadruped",
        category="body",
        limit=2,
    )

    assert rules == {"BODY -> B LEG_PAIR": "Attach legs to body."}
    assert fake_client.calls == [
        ("table", "StructuralRules"),
        ("select", "rule,description"),
        ("eq", "active", True),
        ("eq", "morphology_family", "quadruped"),
        ("eq", "category", "body"),
        ("limit", 2),
    ]


def test_build_query_normalizer_prompt_targets_task_intent():
    prompt = grammar_graph.build_query_normalizer_prompt(
        "make a small quadruped robot that can inspect pipes"
    )

    assert "You are query_normalizer_agent" in prompt
    assert "Return only JSON" in prompt
    assert "TaskIntent" in prompt
    assert "task_goal" in prompt
    assert "hard_constraints" in prompt
    assert "Do not output TaskSpec fields" in prompt
    assert "make a small quadruped robot" in prompt


def test_build_query_normalizer_prompt_rejects_blank_prompt():
    with pytest.raises(ValueError, match="raw_prompt"):
        grammar_graph.build_query_normalizer_prompt("   ")


def test_task_intent_is_frozen():
    intent = TaskIntent(task_goal="make a quadruped")

    with pytest.raises((AttributeError, TypeError)):
        intent.task_goal = "something else"  # type: ignore[misc]


def test_task_intent_typeadapter_roundtrip():
    adapter = TypeAdapter(TaskIntent)
    intent = TaskIntent(
        task_goal="inspect pipes",
        terrain=("rocky", "steep"),
        hard_constraints=("compact body",),
    )

    data = adapter.dump_python(intent)
    assert data["task_goal"] == "inspect pipes"

    restored = adapter.validate_python(data)
    assert restored == intent


def test_infer_morphology_family_keys_off_task_goal():
    assert grammar_graph._infer_morphology_family(TaskIntent(task_goal="quadruped walker")) == "quadruped"
    assert grammar_graph._infer_morphology_family(TaskIntent(task_goal="snake that crawls through pipes")) == "snake"
    assert grammar_graph._infer_morphology_family(TaskIntent(task_goal="humanoid robot for manipulation")) == "humanoid"
    assert grammar_graph._infer_morphology_family(TaskIntent(task_goal="completely novel design")) is None


def test_structural_rule_loop_normalizes_prompt_and_builds_rules(
    monkeypatch: pytest.MonkeyPatch,
):
    class FakeNormalizerAgent:
        def invoke(self, prompt: str):
            assert "query_normalizer_agent" in prompt
            return SimpleNamespace(
                content=(
                    '{"task_goal":"inspect pipes",'
                    '"contact_requirements":["stable locomotion"],'
                    '"hard_constraints":["compact body"]}'
                )
            )

    monkeypatch.setattr(
        grammar_graph,
        "fetch_grammar_from_db",
        lambda **_kwargs: [
            ("S", "Start"),
            ("BODY_CHAIN", "Body Chain"),
            ("BODY_SEG", "Body Segment"),
            ("LEG_PAIR", "Leg Pair"),
        ],
    )
    monkeypatch.setattr(
        grammar_graph,
        "fetch_rules_from_db",
        lambda **_kwargs: {
            "S -> BODY_CHAIN": "Start from a body chain.",
            "BODY_CHAIN -> BODY_SEG LEG_PAIR": "Segment with paired legs.",
        },
    )

    state = grammar_graph.build_structural_rules(
        "inspect pipes with a compact quadruped",
        {"prompt": "", "spec": None, "candidates": []},
        normalizer_agent=FakeNormalizerAgent(),
    )

    assert state["spec"] == TaskIntent(
        task_goal="inspect pipes",
        contact_requirements=("stable locomotion",),
        hard_constraints=("compact body",),
    )
    assert state["prompt"] == "inspect pipes with a compact quadruped"
    assert state["structural_rules"] == {
        "structural_rules": {
            "S": ["BODY_CHAIN"],
            "BODY_CHAIN": ["BODY_SEG", "LEG_PAIR"],
        }
    }
    assert state["compile_result"].compile_safe is True
    assert state["hitl"]["compile_safe"] is True


def test_structural_rule_loop_can_pause_for_human_confirmation():
    state = grammar_graph.build_structural_rules(
        "make a compact snake robot",
        {"prompt": "make a compact snake robot", "candidates": []},
        require_human_confirmation=True,
    )

    assert state["awaiting_human"] is True
    assert state["spec"] == TaskIntent(task_goal="make a compact snake robot")
    assert state["structural_rules"] is None
    assert state["hitl"]["awaiting_human"] is True


def test_initial_checklist_is_authored_by_evaluator_agent(monkeypatch: pytest.MonkeyPatch):
    class FakeRuleBuilderAgent:
        def invoke(self, _messages: object):
            return {"structural_rules": {"S": ["BODY"]}}

    class FakeEvaluatorAgent:
        def __init__(self):
            self.initial_prompt = ""

        def invoke(self, messages: object):
            content = "\n".join(message.content for message in messages)
            if "Create the initial TODO checklist" in content:
                self.initial_prompt = content
                return {
                    "criteria": [
                        {
                            "description": "Rules include a climbing proxy: repeated contact-capable appendage groups.",
                            "isSuccessful": False,
                            "critiques": ["Awaiting rule generation."],
                        }
                    ]
                }
            return {
                "criteria": [
                    {
                        "description": "Rules include a climbing proxy: repeated contact-capable appendage groups.",
                        "isSuccessful": True,
                        "critiques": [],
                    }
                ]
            }

    monkeypatch.setattr(
        grammar_graph,
        "fetch_grammar_from_db",
        lambda **_kwargs: [("S", "Start"), ("BODY", "Body")],
    )
    evaluator_agent = FakeEvaluatorAgent()

    state = grammar_graph.build_structural_rules(
        "make a robot that climbs rocky terrain",
        rule_builder_agent=FakeRuleBuilderAgent(),
        evaluator_agent=evaluator_agent,
    )

    descriptions = [criterion["description"] for criterion in state["checklist"]["criteria"]]
    assert "Create the initial TODO checklist" in evaluator_agent.initial_prompt
    assert all("NormalizedRobotQuery" not in description for description in descriptions)
    assert all("User intent is normalized" not in description for description in descriptions)
    assert descriptions == ["Rules include a climbing proxy: repeated contact-capable appendage groups."]


def test_deterministic_initial_checklist_is_query_specific(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(
        grammar_graph,
        "fetch_grammar_from_db",
        lambda **_kwargs: [
            ("S", "Start"),
            ("BODY_CHAIN", "Body Chain"),
            ("BODY_SEG", "Body Segment"),
            ("LEG_PAIR", "Leg Pair"),
        ],
    )
    monkeypatch.setattr(
        grammar_graph,
        "fetch_rules_from_db",
        lambda **_kwargs: {
            "S -> BODY_CHAIN": "Start recursive body chain.",
            "BODY_CHAIN -> BODY_SEG LEG_PAIR": "Attach paired limbs to body segment.",
        },
    )

    state = grammar_graph.build_structural_rules("make a quadruped that can climb rocky terrain")

    descriptions = [criterion["description"] for criterion in state["checklist"]["criteria"]]
    assert not any("User intent is normalized" in description for description in descriptions)
    assert any("quadruped topology proxy" in description for description in descriptions)
    assert any("climbing proxy" in description for description in descriptions)


def test_langgraph_rule_builder_evaluator_loop_retries_until_compile_safe(
    monkeypatch: pytest.MonkeyPatch,
):
    class FlakyRuleBuilderAgent:
        def __init__(self):
            self.calls = 0
            self.messages: list[object] = []

        def invoke(self, messages: object):
            self.calls += 1
            self.messages.append(messages)
            if self.calls == 1:
                return {"structural_rules": {"S": ["MISSING"]}}
            return {
                "structural_rules": {
                    "S": ["BODY_CHAIN"],
                    "BODY_CHAIN": ["BODY_SEG", "LEG_PAIR"],
                }
            }

    monkeypatch.setattr(
        grammar_graph,
        "fetch_grammar_from_db",
        lambda **_kwargs: [
            ("S", "Start"),
            ("BODY_CHAIN", "Body Chain"),
            ("BODY_SEG", "Body Segment"),
            ("LEG_PAIR", "Leg Pair"),
        ],
    )
    rule_builder_agent = FlakyRuleBuilderAgent()

    state = grammar_graph.build_structural_rules(
        "make a quadruped that can climb rocky terrain",
        rule_builder_agent=rule_builder_agent,
        max_attempts=2,
    )

    assert rule_builder_agent.calls == 2
    assert state["attempts"] == 2
    assert state["compile_result"].compile_safe is True
    second_prompt = rule_builder_agent.messages[1][1].content
    assert '"compile_result": {' in second_prompt
    assert '"invalid_grammar_nodes": [\n      "MISSING"\n    ]' in second_prompt
    assert state["structural_rules"] == {
        "structural_rules": {
            "S": ["BODY_CHAIN"],
            "BODY_CHAIN": ["BODY_SEG", "LEG_PAIR"],
        }
    }


def test_build_checklist_prompt_marks_todo_shape():
    state: grammar_graph.RoboGraphState = {
        "prompt": "make a quadruped",
        "spec": TaskIntent(task_goal="make a quadruped"),
        "structural_rules": {"structural_rules": {"S": ["BODY"]}},
        "candidates": [],
        "checklist": {
            "criteria": [
                {
                    "description": "Structural rules compile against GrammarNodes.",
                    "isSuccessful": False,
                    "critiques": ["Awaiting compiler check."],
                }
            ]
        },
        "compile_result": grammar_graph.CompileResult(False),
    }

    system_message, human_message = grammar_graph.build_checklist_prompt(state)

    assert "evaluator_agent" in system_message.content
    assert "Mark each TODO criterion" in human_message.content
    assert "structural_rules" in human_message.content


def test_compile_structural_rules_accepts_known_nodes(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(
        grammar_graph,
        "fetch_grammar_from_db",
        lambda: [("S", "Start"), ("BODY", "Body"), ("B", "Body Link"), ("LEG", "Leg")],
    )

    result = grammar_graph.compile_structural_rules({"S": ["BODY"], "BODY": ["B", "LEG"]})
    assert result.compile_safe is True
    assert result.invalid_nodes.nodes == ()
    assert result.unreachable_nodes.nodes == ()
    assert result.compile_error is None


def test_structural_rule_state_uses_compile_result_object(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(
        grammar_graph,
        "fetch_grammar_from_db",
        lambda **_kwargs: [("S", "Start"), ("BODY", "Body")],
    )

    state = grammar_graph.build_structural_rules("make a compact robot", max_attempts=1)

    assert state["compile_result"] == grammar_graph.CompileResult(True)
    assert "compile_safe" not in state
    assert "invalid_grammar_nodes" not in state
    assert "unreachable_grammar_nodes" not in state
    assert "compile_error" not in state


def test_compile_attempt_string_includes_parseable_error_context():
    error = {
        "error_type": "RuntimeError",
        "error_message": "supabase-py is required for grammar database access.",
    }
    attempt = grammar_graph.CompileAttempt(
        grammar_graph.CompileResult(
            False,
            grammar_graph.CompilerError(nodes=("TORSO",)),
            grammar_graph.CompilerError(nodes=("FOOT",)),
            compile_error=error,
        )
    )

    message = str(attempt)

    assert "compile_safe=False" in message
    assert "invalid_grammar_nodes=[TORSO]" in message
    assert "unreachable_grammar_nodes=[FOOT]" in message
    assert "compile_error=RuntimeError: supabase-py is required" in message


def test_compile_structural_rules_rejects_unknown_generated_node(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(
        grammar_graph,
        "fetch_grammar_from_db",
        lambda: [("BODY", "Body"), ("B", "Body Link")],
    )

    result = grammar_graph.compile_structural_rules({"BODY": ["B", "WHEEL"]})
    assert result.compile_safe is False
    assert result.invalid_nodes.nodes == ("WHEEL",)


def test_compile_structural_rules_reports_all_invalid_nodes(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(
        grammar_graph,
        "fetch_grammar_from_db",
        lambda: [("BODY", "Body"), ("B", "Body Link")],
    )

    result = grammar_graph.compile_structural_rules(
        {
            "TORSO": ["B", "QUADRUPED_LIMB_PAIR"],
            "BODY": ["LIMB_PAIR", "B"],
        }
    )

    assert result.compile_safe is False
    assert result.invalid_nodes.nodes == ("TORSO", "QUADRUPED_LIMB_PAIR", "LIMB_PAIR")


def test_compile_structural_rules_reports_unreachable_nodes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        grammar_graph,
        "fetch_grammar_from_db",
        lambda: [
            ("S", "Start"),
            ("BODY", "Body"),
            ("LEG", "Leg"),
            ("FOOT", "Foot"),
            ("TAIL", "Tail"),
        ],
    )

    result = grammar_graph.compile_structural_rules(
        {
            "S": ["BODY"],
            "LEG": ["FOOT"],
            "TAIL": ["FOOT"],
        }
    )

    assert result.compile_safe is False
    assert isinstance(result.unreachable_nodes, grammar_graph.CompilerError)
    assert result.unreachable_nodes.nodes == ("FOOT", "LEG", "TAIL")
    assert result.unreachable_nodes.error == {
        "error_type": "UnreachableGrammarNodes",
        "error_message": "Unreachable nodes from S: FOOT, LEG, TAIL",
    }


def test_compile_structural_rules_wraps_invalid_nodes_in_compiler_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        grammar_graph,
        "fetch_grammar_from_db",
        lambda: [("S", "Start"), ("BODY", "Body")],
    )

    result = grammar_graph.compile_structural_rules({"S": ["BODY", "JETPACK"]})

    assert result.compile_safe is False
    assert isinstance(result.invalid_nodes, grammar_graph.CompilerError)
    assert result.invalid_nodes.nodes == ("JETPACK",)
    assert result.invalid_nodes.error == {
        "error_type": "InvalidGrammarNodes",
        "error_message": "Invalid nodes: JETPACK",
    }


def test_compile_structural_rules_exposes_reachability_helper() -> None:
    reachable_nodes = {"S", "BODY"}

    assert grammar_graph._is_reachable("BODY", reachable_nodes) is True
    assert grammar_graph._is_reachable("LEG", reachable_nodes) is False


def test_evaluator_names_invalid_grammar_nodes_in_critique():
    state: grammar_graph.RoboGraphState = {
        "prompt": "make a quadruped",
        "spec": TaskIntent(task_goal="make a quadruped"),
        "structural_rules": {"structural_rules": {"S": ["TORSO"]}},
        "candidates": [],
        "checklist": {
            "criteria": [
                {
                    "description": "Generated structural rules compile against GrammarNodes vocabulary.",
                    "isSuccessful": False,
                    "critiques": ["Awaiting compiler check."],
                }
            ]
        },
        "compile_result": grammar_graph.CompileResult(
            False,
            grammar_graph.CompilerError(nodes=("TORSO", "QUADRUPED_LIMB_PAIR")),
        ),
    }

    checklist = grammar_graph._evaluate_rules_deterministically(state)

    criterion = checklist["criteria"][0]
    assert criterion["isSuccessful"] is False
    assert criterion["critiques"] == [
        "Nodes TORSO, QUADRUPED_LIMB_PAIR were NOT in GrammarNodes vocabulary."
    ]


def test_evaluator_names_unreachable_grammar_nodes_in_critique():
    state: grammar_graph.RoboGraphState = {
        "prompt": "make a stair-climbing quadruped",
        "spec": TaskIntent(task_goal="make a stair-climbing quadruped"),
        "structural_rules": {"structural_rules": {"S": ["BODY"], "LEG": ["FOOT"]}},
        "candidates": [],
        "checklist": {
            "criteria": [
                {
                    "description": "Generated structural rules compile against GrammarNodes vocabulary.",
                    "isSuccessful": False,
                    "critiques": ["Awaiting compiler check."],
                }
            ]
        },
        "compile_result": grammar_graph.CompileResult(
            False,
            grammar_graph.CompilerError(),
            grammar_graph.CompilerError(nodes=("FOOT", "LEG")),
        ),
    }

    checklist = grammar_graph._evaluate_rules_deterministically(state)

    criterion = checklist["criteria"][0]
    assert criterion["isSuccessful"] is False
    assert criterion["critiques"] == [
        "Nodes FOOT, LEG were valid but unreachable from S."
    ]


def test_resolve_grammar_node_name_repairs_close_typo(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(
        grammar_graph,
        "fetch_grammar_from_db",
        lambda **_kwargs: [("LEG_PAIR", "Leg Pair"), ("BODY", "Body")],
    )

    assert grammar_graph.resolve_grammar_node_name("LEG_PAR") == "LEG_PAIR"


def test_resolve_grammar_node_name_matches_long_name_alias(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(
        grammar_graph,
        "fetch_grammar_from_db",
        lambda **_kwargs: [("B", "Body Link"), ("LEG_PAIR", "Leg Pair")],
    )

    assert grammar_graph.resolve_grammar_node_name("Body Link") == "B"


def test_resolve_grammar_node_name_rejects_distant_hallucination(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(
        grammar_graph,
        "fetch_grammar_from_db",
        lambda **_kwargs: [("BODY", "Body"), ("LEG_PAIR", "Leg Pair")],
    )

    assert grammar_graph.resolve_grammar_node_name("QUADRUPED_LEG_PAIR") == ""


def test_langgraph_repairs_fuzzy_node_names_before_compile(
    monkeypatch: pytest.MonkeyPatch,
):
    class TypoRuleBuilderAgent:
        def invoke(self, _messages: object):
            return {"structural_rules": {"S": ["LEG_PAR"]}}

    monkeypatch.setattr(
        grammar_graph,
        "fetch_grammar_from_db",
        lambda **_kwargs: [("S", "Start"), ("LEG_PAIR", "Leg Pair")],
    )

    state = grammar_graph.build_structural_rules(
        "make a robot with paired legs",
        rule_builder_agent=TypoRuleBuilderAgent(),
        max_attempts=1,
    )

    assert state["compile_result"].compile_safe is True
    assert state["structural_rules"] == {"structural_rules": {"S": ["LEG_PAIR"]}}
    assert state["node_resolution"]["corrections"] == [
        {"input": "LEG_PAR", "resolved": "LEG_PAIR"}
    ]


def test_sample_rule_builder_examples_filters_non_compiling_rules(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(
        grammar_graph,
        "fetch_grammar_from_db",
        lambda **_kwargs: [("S", "Start"), ("BODY", "Body"), ("LEG", "Leg")],
    )
    monkeypatch.setattr(
        grammar_graph,
        "fetch_rules_from_db",
        lambda **_kwargs: {
            "S -> BODY LEG": "Valid body with leg.",
            "BODY -> missing_helper LEG": "Invalid helper token.",
        },
    )

    examples = grammar_graph.sample_rule_builder_examples(
        example_families=("quadruped",),
        examples_per_family=2,
    )

    assert examples == {"quadruped": {"S -> BODY LEG": "Valid body with leg."}}


def test_build_rule_builder_system_prompt_injects_vocab_and_examples(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(
        grammar_graph,
        "fetch_grammar_from_db",
        lambda **_kwargs: [
            ("S", "Start"),
            ("TORSO", "Torso"),
            ("LEG_PAIR", "Leg Pair"),
            ("HIP_STACK", "Hip Stack"),
            ("LEG", "Leg"),
        ],
    )

    def fake_fetch_rules_from_db(**kwargs: object):
        family = kwargs["morphology_family"]
        if family == "humanoid":
            return {"S -> TORSO LEG_PAIR": "Humanoid torso with legs."}
        if family == "quadruped":
            return {"LEG -> HIP_STACK": "Quadruped hip stack pattern."}
        return {}

    monkeypatch.setattr(
        grammar_graph,
        "fetch_rules_from_db",
        fake_fetch_rules_from_db,
    )

    query = TaskIntent(
        task_goal="make a stable walker",
        contact_requirements=("stable locomotion",),
        hard_constraints=("use symmetric legs",),
    )

    system_prompt = grammar_graph.build_rule_builder_system_prompt(
        query=query,
        example_families=("humanoid", "quadruped"),
    )

    assert "You are rule_builder_agent" in system_prompt
    assert "Return only JSON" in system_prompt
    assert "S | Start" in system_prompt
    assert "[humanoid]" in system_prompt
    assert "S -> TORSO LEG_PAIR" in system_prompt
    assert "[quadruped]" in system_prompt
    assert "LEG -> HIP_STACK" in system_prompt
    assert "stable locomotion" in system_prompt


def test_build_structural_rules_uses_population_default_and_override(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(
        grammar_graph,
        "fetch_grammar_from_db",
        lambda **_kwargs: [
            ("S", "Start"),
            ("BODY", "Body"),
        ],
    )
    monkeypatch.setattr(
        grammar_graph,
        "fetch_rules_from_db",
        lambda **_kwargs: {
            "S -> BODY": "Minimal body graph.",
        },
    )

    default_state = grammar_graph.build_structural_rules("make a robot")
    custom_state = grammar_graph.build_structural_rules("make a robot", population=4)

    assert default_state["population"] == grammar_graph.DEFAULT_ROBOT_POPULATION
    assert default_state["hitl"]["population"] == grammar_graph.DEFAULT_ROBOT_POPULATION
    assert custom_state["population"] == 4
    assert custom_state["hitl"]["population"] == 4


def test_structural_rule_graph_emits_langsmith_observations(
    monkeypatch: pytest.MonkeyPatch,
):
    observed_names: list[str] = []
    observed_kwargs: dict[str, dict[str, object]] = {}

    class FakeObservation:
        def update(self, **_kwargs: object) -> None:
            return None

    @contextmanager
    def fake_observation(name: str, **_kwargs: object):
        observed_names.append(name)
        observed_kwargs[name] = dict(_kwargs)
        yield FakeObservation()

    monkeypatch.setattr(grammar_graph, "langsmith_observation", fake_observation)
    monkeypatch.setattr(grammar_graph, "get_langsmith_trace_id", lambda: "trace-123")
    monkeypatch.setattr(
        grammar_graph,
        "fetch_grammar_from_db",
        lambda **_kwargs: [("S", "Start"), ("BODY", "Body")],
    )
    monkeypatch.setattr(
        grammar_graph,
        "fetch_rules_from_db",
        lambda **_kwargs: {"S -> BODY": "Minimal graph."},
    )

    state = grammar_graph.build_structural_rules("make a robot")

    assert state["langsmith_trace_id"] == "trace-123"
    assert state["hitl"]["langsmith_trace_id"] == "trace-123"
    assert "robogrammar.structural_rule_graph" in observed_names
    assert "normalize_query" in observed_names
    assert "make_initial_checklist" in observed_names
    assert "build_structural_rules" in observed_names
    assert "resolve_grammar_node_names" in observed_names
    assert observed_kwargs["resolve_grammar_node_names"]["as_type"] == "span"
    assert observed_kwargs["resolve_grammar_node_names"]["metadata"] == {
        "langgraph_node": "resolve_grammar_node_names"
    }
    assert "compile_structural_rules" in observed_names
    assert "evaluate_rules" in observed_names


def test_resolve_node_payload_reports_missing_structural_rules_key():
    with pytest.raises(ValueError, match="resolve_grammar_node_names"):
        grammar_graph._rules_payload_for_node_resolution({"rules": {"S": ["BODY"]}})


def test_resolve_node_payload_reports_malformed_rhs():
    with pytest.raises(ValueError, match="RHS is str, not list"):
        grammar_graph._rules_payload_for_node_resolution(
            {"structural_rules": {"S": "BODY"}}
        )


def test_resolve_node_keeps_rules_when_grammar_db_unavailable(
    monkeypatch: pytest.MonkeyPatch,
):
    class RuleBuilderAgent:
        def invoke(self, _messages: object):
            return {"structural_rules": {"S": ["BODY"]}}

    def raise_missing_supabase(*_args: object, **_kwargs: object):
        raise RuntimeError("supabase-py is required for grammar database access.")

    monkeypatch.setattr(grammar_graph, "fetch_grammar_from_db", raise_missing_supabase)

    state = grammar_graph.build_structural_rules(
        "make a robot",
        rule_builder_agent=RuleBuilderAgent(),
        max_attempts=1,
    )

    assert state["structural_rules"] == {"structural_rules": {"S": ["BODY"]}}
    assert state["node_resolution"]["status"] == "skipped"
    assert state["node_resolution"]["error_type"] == "RuntimeError"
    assert "supabase-py is required" in state["node_resolution"]["error_message"]
    assert state["compile_result"].compile_safe is False
    assert state["compile_result"].compile_error == {
        "error_type": "RuntimeError",
        "error_message": "supabase-py is required for grammar database access.",
    }
    assert state["hitl"]["compile_error"] == state["compile_result"].compile_error


def test_repair_node_names_is_best_effort_when_grammar_db_unavailable(
    monkeypatch: pytest.MonkeyPatch,
):
    def raise_missing_supabase(*_args: object, **_kwargs: object):
        raise RuntimeError("supabase-py is required for grammar database access.")

    monkeypatch.setattr(grammar_graph, "fetch_grammar_from_db", raise_missing_supabase)

    rules = {"SHANK": ["JOINT"], "FOOT": []}
    repaired, resolution = grammar_graph.repair_structural_rule_node_names(rules)

    assert repaired == rules
    assert resolution["status"] == "skipped"
    assert resolution["unresolved"] == ["FOOT", "JOINT", "SHANK"]
    assert resolution["error_type"] == "RuntimeError"
    assert "supabase-py is required" in resolution["error_message"]


def test_requested_functions_are_registered_in_tools():
    assert grammar_graph.tools == [
        grammar_graph.fetch_grammar_from_db,
        grammar_graph.fetch_desc_by_node,
        grammar_graph.fetch_rules_from_db,
        grammar_graph.resolve_grammar_node_name,
        grammar_graph.compile_structural_rules,
    ]


class FakeSupabaseClient:
    def __init__(
        self,
        rows: list[dict[str, object]] | dict[str, list[dict[str, object]]],
    ):
        self.rows = rows
        self.calls: list[tuple[str, object] | tuple[str, object, object]] = []

    def table(self, table_name: str):
        self.calls.append(("table", table_name))
        return FakeSupabaseQuery(self, table_name)


class FakeSupabaseQuery:
    def __init__(self, client: FakeSupabaseClient, table_name: str):
        self.client = client
        self.table_name = table_name

    def select(self, columns: str):
        self.client.calls.append(("select", columns))
        return self

    def eq(self, column: str, value: object):
        self.client.calls.append(("eq", column, value))
        return self

    def limit(self, limit: int):
        self.client.calls.append(("limit", limit))
        return self

    def execute(self):
        if isinstance(self.client.rows, dict):
            return SimpleNamespace(data=self.client.rows.get(self.table_name, []))
        return SimpleNamespace(data=self.client.rows)
