from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import pytest

from packages.pipeline.schemas import TaskIntent
from packages.research.local_chat_models import (
    LocalAIMessage,
    LocalChatModel,
    LocalModelConfig,
    LocalStructuredChatModel,
    OpenAICompatibleChatModel,
    default_local_command,
    make_chat_model,
    _model_output_payload,
)


def test_local_structured_model_reuses_one_persistent_jsonl_process(tmp_path: Path) -> None:
    starts_path = tmp_path / "starts.txt"
    script_path = tmp_path / "fake_model.py"
    script_path.write_text(
        "\n".join(
            [
                "import json",
                "import sys",
                f"open({str(starts_path)!r}, 'a').write('start\\n')",
                "for line in sys.stdin:",
                "    payload = json.loads(line)",
                "    print(json.dumps({'content': json.dumps({'task_goal': payload['prompt'].splitlines()[0]})}), flush=True)",
            ]
        )
    )

    model = LocalChatModel(
        LocalModelConfig(
            provider="test-jsonl",
            command=(sys.executable, str(script_path)),
            protocol="jsonl",
        )
    ).with_structured_output(TaskIntent)

    first = model.invoke("walk over rocks")
    second = model.invoke("carry a payload")

    assert first.task_goal == "walk over rocks"
    assert second.task_goal == "carry a payload"
    assert starts_path.read_text().splitlines() == ["start"]


def test_claude_code_default_command_uses_noninteractive_json() -> None:
    command = default_local_command("claude-code", "claude-sonnet-4-5")

    assert command[0] == "claude"
    assert "-p" in command
    assert "--output-format" in command
    assert "json" in command
    assert "--model" in command
    assert "claude-sonnet-4-5" in command


def test_codex_default_command_uses_persistent_mcp_server() -> None:
    command = default_local_command("codex", "gpt-5.4")

    assert command[:2] == ("codex", "mcp-server")
    assert "mcp_servers={}" in command
    assert "plugins={}" in command
    assert "marketplaces={}" in command


def test_codex_mcp_protocol_continues_thread(tmp_path: Path) -> None:
    calls_path = tmp_path / "calls.jsonl"
    script_path = tmp_path / "fake_codex_mcp.py"
    script_path.write_text(
        "\n".join(
            [
                "import json",
                "import sys",
                f"calls_path = {str(calls_path)!r}",
                "for line in sys.stdin:",
                "    message = json.loads(line)",
                "    method = message.get('method')",
                "    if method == 'initialize':",
                "        print(json.dumps({'jsonrpc': '2.0', 'id': message['id'], 'result': {'protocolVersion': '2025-06-18', 'capabilities': {'tools': {}}, 'serverInfo': {'name': 'fake-codex'}}}), flush=True)",
                "    elif method == 'notifications/initialized':",
                "        continue",
                "    elif method == 'tools/call':",
                "        params = message['params']",
                "        with open(calls_path, 'a') as f:",
                "            f.write(json.dumps(params) + '\\n')",
                "        name = params['name']",
                "        thread_id = 'thread-1'",
                "        content = 'first' if name == 'codex' else 'second'",
                "        result = {'content': [{'type': 'text', 'text': content}], 'structuredContent': {'threadId': thread_id, 'content': content}}",
                "        print(json.dumps({'jsonrpc': '2.0', 'id': message['id'], 'result': result}), flush=True)",
            ]
        )
    )

    model = LocalChatModel(
        LocalModelConfig(
            provider="codex",
            model="gpt-5.4",
            command=(sys.executable, str(script_path)),
            protocol="mcp-jsonrpc",
            cwd=str(tmp_path),
        )
    )

    first = model.invoke("one")
    second = model.invoke("two")

    calls = [json.loads(line) for line in calls_path.read_text().splitlines()]
    assert first.content == "first"
    assert second.content == "second"
    assert calls[0]["name"] == "codex"
    assert calls[0]["arguments"]["model"] == "gpt-5.4"
    assert calls[0]["arguments"]["approval-policy"] == "never"
    assert calls[0]["arguments"]["config"]["mcp_servers"] == {}
    assert calls[0]["arguments"]["config"]["plugins"] == {}
    assert calls[1]["name"] == "codex-reply"
    assert calls[1]["arguments"]["threadId"] == "thread-1"
    assert "model" not in calls[1]["arguments"]


def test_make_chat_model_selects_local_provider_from_env(monkeypatch) -> None:
    monkeypatch.setenv("RESEARCH_LLM_PROVIDER", "claude-code")
    monkeypatch.setenv("RESEARCH_LLM_MODEL", "claude-sonnet-4-5")

    model = make_chat_model()

    assert isinstance(model, LocalChatModel)
    assert model.config.provider == "claude-code"
    assert model.config.model == "claude-sonnet-4-5"
    assert model.config.protocol == "claude-print-json"


def test_make_chat_model_selects_openai_compatible_provider(monkeypatch) -> None:
    monkeypatch.setenv("RESEARCH_LLM_PROVIDER", "openai-compatible")
    monkeypatch.setenv("RESEARCH_LLM_MODEL", "Qwen/Qwen3-1.7B")
    monkeypatch.setenv("RESEARCH_LLM_BASE_URL", "http://127.0.0.1:8001/v1")
    monkeypatch.setenv("RESEARCH_LLM_API_KEY", "EMPTY")

    model = make_chat_model()

    assert isinstance(model, OpenAICompatibleChatModel)
    assert model.config.provider == "openai-compatible"
    assert model.config.model == "Qwen/Qwen3-1.7B"
    assert model.config.protocol == "openai-chat-completions"
    assert model.base_url == "http://127.0.0.1:8001/v1"


def test_openai_compatible_model_respects_max_tokens_env(monkeypatch) -> None:
    monkeypatch.setenv("RESEARCH_LLM_MAX_TOKENS", "64")
    calls = []

    class FakeCompletions:
        def create(self, **kwargs):
            calls.append(kwargs)
            message = type("Message", (), {"content": '{"task_goal": "ok"}'})()
            choice = type("Choice", (), {"message": message})()
            return type("Completion", (), {"choices": [choice]})()

    class FakeClient:
        chat = type(
            "Chat",
            (),
            {"completions": FakeCompletions()},
        )()

    model = OpenAICompatibleChatModel(
        LocalModelConfig(
            provider="openai-compatible",
            model="fake",
            protocol="openai-chat-completions",
        ),
        base_url="http://127.0.0.1:8001/v1",
        api_key="EMPTY",
    )
    model._client = FakeClient()

    model.invoke("hello")

    assert calls[0]["max_tokens"] == 64


def test_claude_print_json_protocol_reads_result(tmp_path: Path) -> None:
    script_path = tmp_path / "fake_claude.py"
    script_path.write_text(
        "\n".join(
            [
                "import json",
                "import sys",
                "print(json.dumps({'type': 'result', 'is_error': False, 'result': sys.stdin.read().upper()}))",
            ]
        )
    )
    model = LocalChatModel(
        LocalModelConfig(
            provider="claude-code",
            command=(sys.executable, str(script_path)),
            protocol="claude-print-json",
        )
    )

    assert model.invoke("hello").content == "HELLO"


def test_model_output_payload_decomposes_fenced_json() -> None:
    payload = _model_output_payload(
        '```json\n{"criteria": [{"description": "ok", "isSuccessful": true}]}\n```'
    )

    assert payload == {
        "criteria": [{"description": "ok", "isSuccessful": True}]
    }


def test_model_output_payload_decomposes_python_literal_dict() -> None:
    payload = _model_output_payload(
        "{'structural_rules': {'S': ['BODY'], 'BODY': ['BODY_SEG']}}"
    )

    assert payload == {
        "structural_rules": {"S": ["BODY"], "BODY": ["BODY_SEG"]}
    }


def test_local_structured_model_accepts_python_literal_dict_response() -> None:
    class FakeModel:
        config = LocalModelConfig(provider="test", model="fake")

        def invoke(self, _prompt, config=None):
            return LocalAIMessage(content="{'task_goal': 'walk over rocks'}")

    model = LocalStructuredChatModel(FakeModel(), TaskIntent)

    assert model.invoke("walk over rocks").task_goal == "walk over rocks"


def test_grammar_loop_coerces_python_literal_structural_rules() -> None:
    from packages.research.agent_loops.grammar_loop import _coerce_structural_rules

    message = LocalAIMessage(
        content="{'structural_rules': {'S': ['BODY'], 'BODY': ['BODY_SEG']}}"
    )

    assert _coerce_structural_rules(message) == {
        "structural_rules": {"S": ["BODY"], "BODY": ["BODY_SEG"]}
    }


def test_make_chat_model_without_provider_does_not_default_to_openai(monkeypatch) -> None:
    monkeypatch.delenv("RESEARCH_LLM_PROVIDER", raising=False)
    monkeypatch.delenv("LOCAL_LLM_PROVIDER", raising=False)
    monkeypatch.delenv("RESEARCH_LLM_MODEL", raising=False)
    monkeypatch.delenv("OPENAI_MODEL", raising=False)

    assert make_chat_model("gpt-4.1-mini") is None


def test_local_jsonl_process_respects_timeout(tmp_path: Path) -> None:
    script_path = tmp_path / "slow_model.py"
    script_path.write_text("import time\ntime.sleep(0.3)\n")
    model = LocalChatModel(
        LocalModelConfig(
            provider="test-jsonl",
            command=(sys.executable, str(script_path)),
            protocol="jsonl",
            timeout_seconds=0.01,
        )
    )

    started = time.monotonic()
    with pytest.raises(Exception):
        model.invoke("hello")

    assert time.monotonic() - started < 0.15


def test_research_chat_model_factories_use_local_provider(monkeypatch) -> None:
    monkeypatch.setenv("RESEARCH_LLM_PROVIDER", "codex")
    monkeypatch.setenv("RESEARCH_LLM_MODEL", "gpt-5-codex")

    from packages.research.agent_loops import grammar_loop
    from packages.research.strategy import llm_materializer, prompt_agents

    grammar_agent = grammar_loop._make_structured_agent(TaskIntent)
    prompt_agent = prompt_agents._make_structured_llm("ignored", TaskIntent)
    materializer_model = llm_materializer._make_llm("ignored")

    assert isinstance(grammar_agent, LocalStructuredChatModel)
    assert isinstance(prompt_agent, LocalStructuredChatModel)
    assert isinstance(materializer_model, LocalChatModel)
    assert materializer_model.config.model == "gpt-5-codex"
