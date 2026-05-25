"""Local ChatOpenAI-compatible adapters for research loops.

The research layer only needs the small part of the LangChain chat-model
surface used by the grammar loop: ``invoke(...)`` and
``with_structured_output(schema)``. This module provides that surface for local
Claude Code / Codex subprocesses so experiments can avoid OpenAI API calls.
"""

from __future__ import annotations

import ast
import json
import os
import select
import shlex
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from pydantic import TypeAdapter

from packages.pipeline.observability import langsmith_observation

ProtocolName = Literal[
    "jsonl",
    "sentinel",
    "mcp-jsonrpc",
    "claude-print-json",
    "openai-chat-completions",
]

DEFAULT_QWEN_MODEL_ID = "Qwen/Qwen3-1.7B"
DEFAULT_OPENAI_COMPATIBLE_BASE_URL = "http://127.0.0.1:8001/v1"

_CODEX_SESSION_CONFIG: dict[str, Any] = {
    "mcp_servers": {},
    "plugins": {},
    "marketplaces": {},
    "features": {
        "external_migration": False,
        "memories": False,
    },
}


@dataclass(frozen=True)
class LocalAIMessage:
    """Minimal message object compatible with code that reads ``.content``."""

    content: str


@dataclass(frozen=True)
class LocalModelConfig:
    """Configuration for a local persistent CLI-backed chat model."""

    provider: str
    model: str | None = None
    command: tuple[str, ...] | None = None
    protocol: ProtocolName = "sentinel"
    cwd: str | None = None
    timeout_seconds: float = 120.0


class LocalModelError(RuntimeError):
    """Raised when a local model process cannot produce a usable response."""


class LocalChatModel:
    """Small ChatOpenAI-compatible wrapper around one persistent subprocess."""

    def __init__(self, config: LocalModelConfig) -> None:
        self.config = config
        self._process: _PersistentLocalProcess | None = None

    def invoke(self, messages: Any, config: dict[str, Any] | None = None) -> LocalAIMessage:
        prompt = _messages_to_prompt(messages)
        metadata = {
            "provider": self.config.provider,
            "model": self.config.model,
            "protocol": self.config.protocol,
        }
        with langsmith_observation(
            f"local_model.{self.config.provider}",
            as_type="llm",
            input={"prompt": prompt},
            metadata=metadata,
        ) as observation:
            if self.config.protocol == "claude-print-json":
                content = _request_claude_print_json(self.config, prompt)
            else:
                content = self._client().request(prompt)
            observation.update(output=_model_output_payload(content))
            return LocalAIMessage(content=content)

    def with_structured_output(self, schema: Any) -> "LocalStructuredChatModel":
        return LocalStructuredChatModel(self, schema)

    def close(self) -> None:
        if self._process is not None:
            self._process.close()
            self._process = None

    def _client(self) -> "_PersistentLocalProcess":
        if self._process is None:
            command = self.config.command or default_local_command(
                self.config.provider,
                self.config.model,
            )
            self._process = _PersistentLocalProcess(
                command=command,
                protocol=self.config.protocol,
                cwd=self.config.cwd,
                model=self.config.model,
                timeout_seconds=self.config.timeout_seconds,
            )
        return self._process


class OpenAICompatibleChatModel:
    """Small chat wrapper for local OpenAI-compatible HTTP servers."""

    def __init__(self, config: LocalModelConfig, *, base_url: str, api_key: str) -> None:
        self.config = config
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self._client: Any | None = None

    def invoke(self, messages: Any, config: dict[str, Any] | None = None) -> LocalAIMessage:
        request_messages = _messages_to_openai_messages(messages)
        metadata = {
            "provider": self.config.provider,
            "model": self.config.model,
            "base_url": self.base_url,
        }
        with langsmith_observation(
            f"local_model.{self.config.provider}",
            as_type="llm",
            input={"messages": request_messages},
            metadata=metadata,
        ) as observation:
            completion_kwargs: dict[str, Any] = {
                "model": self.config.model or DEFAULT_QWEN_MODEL_ID,
                "messages": request_messages,
                "timeout": self.config.timeout_seconds,
            }
            max_tokens = _optional_int_from_env("RESEARCH_LLM_MAX_TOKENS")
            if max_tokens is not None:
                completion_kwargs["max_tokens"] = max_tokens
            completion = self._openai_client().chat.completions.create(
                **completion_kwargs,
            )
            message = completion.choices[0].message
            content = getattr(message, "content", None)
            if not isinstance(content, str):
                raise LocalModelError("OpenAI-compatible model response had no text content.")
            observation.update(output=_model_output_payload(content))
            return LocalAIMessage(content=content)

    def with_structured_output(self, schema: Any) -> "LocalStructuredChatModel":
        return LocalStructuredChatModel(self, schema)

    def close(self) -> None:
        self._client = None

    def _openai_client(self) -> Any:
        if self._client is None:
            try:
                from openai import OpenAI
            except ImportError as exc:  # pragma: no cover - dependency guard
                raise LocalModelError(
                    "The 'openai' package is required for RESEARCH_LLM_PROVIDER="
                    "'openai-compatible'."
                ) from exc
            self._client = OpenAI(base_url=self.base_url, api_key=self.api_key)
        return self._client


class LocalStructuredChatModel:
    """Structured-output wrapper matching ``ChatOpenAI.with_structured_output``."""

    def __init__(self, model: Any, schema: Any) -> None:
        self._model = model
        self._schema = schema
        self._adapter = TypeAdapter(schema)

    def invoke(self, messages: Any, config: dict[str, Any] | None = None) -> Any:
        schema_json = json.dumps(self._adapter.json_schema(), indent=2)
        prompt = "\n\n".join(
            [
                _messages_to_prompt(messages),
                "Return only one JSON object matching this schema.",
                schema_json,
            ]
        )
        schema_name = getattr(self._schema, "__name__", str(self._schema))
        with langsmith_observation(
            f"structured_output.{schema_name}",
            as_type="chain",
            input={"prompt": prompt, "schema": self._adapter.json_schema()},
            metadata={
                "provider": self._model.config.provider,
                "model": self._model.config.model,
            },
        ) as observation:
            response = self._model.invoke(prompt, config=config)
            payload = _extract_json_payload(response.content)
            validated = self._adapter.validate_python(payload)
            if hasattr(validated, "model_dump"):
                output = validated.model_dump()
            else:
                output = payload
            observation.update(output=output if isinstance(output, dict) else {"output": output})
            return validated


class _PersistentLocalProcess:
    """Persistent line-oriented subprocess used by ``LocalChatModel``."""

    def __init__(
        self,
        *,
        command: tuple[str, ...],
        protocol: ProtocolName,
        cwd: str | None,
        model: str | None,
        timeout_seconds: float,
    ) -> None:
        self._command = command
        self._protocol = protocol
        self._cwd = cwd
        self._model = model
        self._timeout_seconds = timeout_seconds
        self._next_request_id = 0
        self._thread_id: str | None = None
        self._process = subprocess.Popen(
            command,
            cwd=cwd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
        )
        if self._protocol == "mcp-jsonrpc":
            self._initialize_mcp()

    def request(self, prompt: str) -> str:
        if self._process.poll() is not None:
            raise LocalModelError(
                f"Local model process exited with code {self._process.returncode}: "
                f"{self._read_stderr()}"
            )
        if self._protocol == "jsonl":
            return self._request_jsonl(prompt)
        if self._protocol == "mcp-jsonrpc":
            return self._request_mcp(prompt)
        return self._request_sentinel(prompt)

    def close(self) -> None:
        if self._process.poll() is None:
            self._process.terminate()
            try:
                self._process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                self._process.kill()

    def _request_jsonl(self, prompt: str) -> str:
        assert self._process.stdin is not None
        assert self._process.stdout is not None
        self._process.stdin.write(json.dumps({"prompt": prompt}) + "\n")
        self._process.stdin.flush()

        deadline = time.monotonic() + self._timeout_seconds
        while time.monotonic() < deadline:
            line = self._read_stdout_line(deadline)
            if line is None:
                continue
            if not line:
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                continue
            content = payload.get("content", payload.get("response"))
            if isinstance(content, str):
                return content
        self.close()
        raise LocalModelError(
            "Timed out waiting for local JSONL model response. "
            f"stderr: {self._read_stderr()}"
        )

    def _initialize_mcp(self) -> None:
        init_id = self._next_id()
        self._send_json(
            {
                "jsonrpc": "2.0",
                "id": init_id,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2025-06-18",
                    "capabilities": {},
                    "clientInfo": {
                        "name": "il-ideation-local-chat-model",
                        "version": "0.1.0",
                    },
                },
            }
        )
        self._read_jsonrpc_response(init_id, "initialize")
        self._send_json(
            {
                "jsonrpc": "2.0",
                "method": "notifications/initialized",
                "params": {},
            }
        )

    def _request_mcp(self, prompt: str) -> str:
        request_id = self._next_id()
        if self._thread_id:
            tool_name = "codex-reply"
            arguments = {
                "threadId": self._thread_id,
                "prompt": prompt,
            }
        else:
            tool_name = "codex"
            arguments = {
                "prompt": prompt,
                "cwd": self._cwd or str(Path.cwd()),
                "sandbox": "read-only",
                "approval-policy": "never",
                "config": _CODEX_SESSION_CONFIG,
            }
            if self._model:
                arguments["model"] = self._model

        self._send_json(
            {
                "jsonrpc": "2.0",
                "id": request_id,
                "method": "tools/call",
                "params": {
                    "name": tool_name,
                    "arguments": self._mcp_arguments(arguments),
                },
            }
        )
        payload = self._read_jsonrpc_response(request_id, tool_name)
        result = payload.get("result")
        if not isinstance(result, dict):
            raise LocalModelError(f"Local MCP model returned no result: {payload}")
        structured = result.get("structuredContent")
        if isinstance(structured, dict):
            thread_id = structured.get("threadId")
            content = structured.get("content")
            if isinstance(thread_id, str):
                self._thread_id = thread_id
            if isinstance(content, str):
                return content
        content_blocks = result.get("content")
        if isinstance(content_blocks, list):
            text_parts = [
                block.get("text")
                for block in content_blocks
                if isinstance(block, dict) and isinstance(block.get("text"), str)
            ]
            if text_parts:
                return "\n".join(text_parts)
        raise LocalModelError(f"Local MCP model response had no text content: {result}")

    def _mcp_arguments(self, arguments: dict[str, Any]) -> dict[str, Any]:
        if "cwd" in arguments and self._cwd:
            arguments["cwd"] = self._cwd
        return arguments

    def _next_id(self) -> int:
        self._next_request_id += 1
        return self._next_request_id

    def _send_json(self, payload: dict[str, Any]) -> None:
        assert self._process.stdin is not None
        self._process.stdin.write(json.dumps(payload) + "\n")
        self._process.stdin.flush()

    def _read_jsonrpc_response(self, request_id: int, label: str) -> dict[str, Any]:
        deadline = time.monotonic() + self._timeout_seconds
        while time.monotonic() < deadline:
            line = self._read_stdout_line(deadline)
            if line is None or not line:
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                continue
            if payload.get("id") == request_id:
                if "error" in payload:
                    raise LocalModelError(
                        f"Local MCP model failed during {label}: {payload['error']}"
                    )
                return payload
        self.close()
        raise LocalModelError(
            f"Timed out waiting for local MCP response to {label}. "
            f"stderr: {self._read_stderr()}"
        )

    def _request_sentinel(self, prompt: str) -> str:
        assert self._process.stdin is not None
        assert self._process.stdout is not None
        sentinel = f"<<<LOCAL_CHAT_RESPONSE_{time.time_ns()}>>>"
        self._process.stdin.write(
            "\n\n".join(
                [
                    prompt,
                    "Return the final answer as plain text.",
                    f"End the final answer with this exact sentinel on its own line: {sentinel}",
                ]
            )
            + "\n"
        )
        self._process.stdin.flush()

        chunks: list[str] = []
        deadline = time.monotonic() + self._timeout_seconds
        while time.monotonic() < deadline:
            line = self._read_stdout_line(deadline)
            if line is None:
                continue
            if not line:
                continue
            chunks.append(line)
            if sentinel in line:
                content = "".join(chunks).split(sentinel, 1)[0].strip()
                return content
        self.close()
        raise LocalModelError(
            "Timed out waiting for local sentinel model response. "
            f"stderr: {self._read_stderr()}"
        )

    def _read_stdout_line(self, deadline: float) -> str | None:
        assert self._process.stdout is not None
        remaining = max(0.0, deadline - time.monotonic())
        if remaining <= 0:
            return None
        ready, _, _ = select.select(
            [self._process.stdout],
            [],
            [],
            min(0.05, remaining),
        )
        if not ready:
            if self._process.poll() is not None:
                return ""
            return None
        return self._process.stdout.readline()

    def _read_stderr(self) -> str:
        stderr = self._process.stderr
        if stderr is None:
            return ""
        return stderr.read() if self._process.poll() is not None else ""


def make_chat_model(
    model_id: str | None = None,
    *,
    provider: str | None = None,
) -> Any | None:
    """Return a chat model from env/config.

    OpenAI is intentionally opt-in. If no provider is configured, callers get
    ``None`` and can use deterministic fallbacks without accidentally hitting
    the OpenAI API.
    """

    raw_provider = (
        provider
        or os.environ.get("RESEARCH_LLM_PROVIDER")
        or os.environ.get("LOCAL_LLM_PROVIDER")
    )
    resolved_provider = raw_provider.strip() if raw_provider else ""
    if not resolved_provider:
        return None
    env_model = os.environ.get("RESEARCH_LLM_MODEL")
    openai_env_model = os.environ.get("OPENAI_MODEL")

    if resolved_provider in {"claude", "claude-code", "claude_code", "codex"}:
        resolved_model = env_model or model_id
        command = _command_from_env() or default_local_command(
            _canonical_provider(resolved_provider),
            resolved_model,
        )
        return LocalChatModel(
            LocalModelConfig(
                provider=_canonical_provider(resolved_provider),
                model=resolved_model,
                command=command,
                protocol=_protocol_from_env(command),
                cwd=os.environ.get("RESEARCH_LLM_CWD") or str(Path.cwd()),
                timeout_seconds=float(os.environ.get("RESEARCH_LLM_TIMEOUT", "120")),
            )
        )

    if resolved_provider in {
        "openai-compatible",
        "openai_compatible",
        "qwen",
        "qwen-openai",
        "qwen_openai",
    }:
        resolved_model = (
            model_id
            or env_model
            or os.environ.get("QWEN_MODEL_ID")
            or openai_env_model
            or DEFAULT_QWEN_MODEL_ID
        )
        return OpenAICompatibleChatModel(
            LocalModelConfig(
                provider="openai-compatible",
                model=resolved_model,
                protocol="openai-chat-completions",
                timeout_seconds=float(os.environ.get("RESEARCH_LLM_TIMEOUT", "120")),
            ),
            base_url=(
                os.environ.get("RESEARCH_LLM_BASE_URL")
                or os.environ.get("OPENAI_BASE_URL")
                or DEFAULT_OPENAI_COMPATIBLE_BASE_URL
            ),
            api_key=(
                os.environ.get("RESEARCH_LLM_API_KEY")
                or os.environ.get("OPENAI_API_KEY")
                or "EMPTY"
            ),
        )

    if resolved_provider != "openai":
        raise ValueError(
            "RESEARCH_LLM_PROVIDER must be 'codex', 'claude-code', "
            "'openai-compatible', or 'openai'."
        )

    try:
        from langchain_openai import ChatOpenAI

        resolved_model = model_id or env_model or openai_env_model
        return ChatOpenAI(model=resolved_model or "gpt-4.1-mini")
    except Exception:
        return None


def make_structured_llm(
    model_id: str | None,
    schema: Any,
    *,
    provider: str | None = None,
) -> Any | None:
    model = make_chat_model(model_id, provider=provider)
    if model is None:
        return None
    return model.with_structured_output(schema)


def default_local_command(provider: str, model: str | None = None) -> tuple[str, ...]:
    """Build the default persistent CLI command for a local provider."""

    canonical = _canonical_provider(provider)
    if canonical == "claude-code":
        return (
            "claude",
            "-p",
            "--output-format",
            "json",
            "--model",
            model or "claude-sonnet-4-5",
            "--tools",
            "",
        )
    if canonical == "codex":
        return (
            "codex",
            "mcp-server",
            "-c",
            "mcp_servers={}",
            "-c",
            "plugins={}",
            "-c",
            "marketplaces={}",
            "-c",
            "features.external_migration=false",
            "-c",
            "features.memories=false",
        )
    raise ValueError(f"Unknown local model provider: {provider}")


def _canonical_provider(provider: str) -> str:
    if provider in {"claude", "claude_code"}:
        return "claude-code"
    return provider


def _command_from_env() -> tuple[str, ...] | None:
    raw = os.environ.get("RESEARCH_LLM_COMMAND") or os.environ.get("LOCAL_LLM_COMMAND")
    return tuple(shlex.split(raw)) if raw else None


def _protocol_from_env(command: tuple[str, ...] | None) -> ProtocolName:
    raw = os.environ.get("RESEARCH_LLM_PROTOCOL") or os.environ.get("LOCAL_LLM_PROTOCOL")
    if raw:
        if raw not in {"jsonl", "sentinel", "claude-print-json"}:
            if raw != "mcp-jsonrpc":
                raise ValueError(
                    "RESEARCH_LLM_PROTOCOL must be 'jsonl', 'sentinel', "
                    "'claude-print-json', or 'mcp-jsonrpc'."
                )
        return raw  # type: ignore[return-value]
    if command and tuple(command[:2]) == ("codex", "mcp-server"):
        return "mcp-jsonrpc"
    if command and Path(command[0]).name == "claude" and "-p" in command:
        return "claude-print-json"
    return "jsonl" if command else "sentinel"


def _optional_int_from_env(name: str) -> int | None:
    raw = os.environ.get(name)
    if raw is None or not raw.strip():
        return None
    value = int(raw)
    return value if value > 0 else None


def _request_claude_print_json(config: LocalModelConfig, prompt: str) -> str:
    command = tuple(config.command or default_local_command(config.provider, config.model))
    try:
        completed = subprocess.run(
            command,
            cwd=config.cwd,
            env=_claude_subprocess_env() if config.provider == "claude-code" else None,
            input=prompt,
            text=True,
            capture_output=True,
            timeout=config.timeout_seconds,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise LocalModelError("Timed out waiting for Claude Code print response.") from exc

    raw = completed.stdout.strip()
    payload: dict[str, Any] = {}
    if raw:
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, dict):
                payload = parsed
        except json.JSONDecodeError:
            if completed.returncode == 0:
                return raw
    if completed.returncode != 0 or payload.get("is_error"):
        error = payload.get("result") or completed.stderr.strip() or raw
        raise LocalModelError(f"Claude Code local model failed: {error}")
    result = payload.get("result")
    if isinstance(result, str):
        return result
    raise LocalModelError(f"Claude Code local model returned no text result: {payload or raw}")


def _claude_subprocess_env() -> dict[str, str]:
    env = os.environ.copy()
    if os.environ.get("RESEARCH_LLM_USE_ANTHROPIC_API_KEY", "0").strip().lower() not in {
        "1",
        "true",
        "yes",
        "on",
    }:
        env.pop("ANTHROPIC_API_KEY", None)
    return env


def _messages_to_prompt(messages: Any) -> str:
    if isinstance(messages, str):
        return messages
    if isinstance(messages, list):
        return "\n\n".join(_message_to_text(message) for message in messages)
    if isinstance(messages, dict):
        return json.dumps(messages, indent=2, default=str)
    return _message_to_text(messages)


def _message_to_text(message: Any) -> str:
    content = getattr(message, "content", None)
    if isinstance(content, str):
        return content
    if isinstance(message, dict) and isinstance(message.get("content"), str):
        return message["content"]
    return str(message)


def _messages_to_openai_messages(messages: Any) -> list[dict[str, str]]:
    if isinstance(messages, str):
        return [{"role": "user", "content": messages}]
    if isinstance(messages, list):
        return [_message_to_openai_message(message) for message in messages]
    if isinstance(messages, dict) and isinstance(messages.get("messages"), list):
        return [_message_to_openai_message(message) for message in messages["messages"]]
    return [{"role": "user", "content": _message_to_text(messages)}]


def _message_to_openai_message(message: Any) -> dict[str, str]:
    role = "user"
    content = _message_to_text(message)
    if isinstance(message, dict):
        raw_role = message.get("role") or message.get("type")
        if isinstance(raw_role, str):
            role = _normalize_openai_role(raw_role)
    else:
        raw_role = getattr(message, "role", None) or getattr(message, "type", None)
        if isinstance(raw_role, str):
            role = _normalize_openai_role(raw_role)
    return {"role": role, "content": content}


def _normalize_openai_role(role: str) -> str:
    normalized = role.lower().replace("_", "-")
    if normalized in {"human", "user"}:
        return "user"
    if normalized in {"ai", "assistant"}:
        return "assistant"
    if normalized in {"system", "developer"}:
        return "system"
    if normalized == "tool":
        return "user"
    return "user"


def _extract_json_payload(content: str) -> Any:
    parsed = _loads_structured_text(content)
    if parsed is not None:
        return parsed

    stripped = content.strip()
    if stripped.startswith("```"):
        stripped = stripped.strip("`")
        newline = stripped.find("\n")
        if newline >= 0:
            stripped = stripped[newline + 1 :]
        parsed = _loads_structured_text(stripped)
        if parsed is not None:
            return parsed

    start = content.find("{")
    end = content.rfind("}") + 1
    if start >= 0 and end > start:
        parsed = _loads_structured_text(content[start:end])
        if parsed is not None:
            return parsed
    raise LocalModelError("Local model response did not contain a JSON object.")


def _loads_structured_text(text: str) -> Any | None:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    try:
        return ast.literal_eval(text)
    except (SyntaxError, ValueError):
        return None


def _model_output_payload(content: str) -> dict[str, Any]:
    try:
        payload = _extract_json_payload(content)
    except Exception:
        return {"content": content}
    if isinstance(payload, dict):
        return payload
    return {"output": payload}


__all__ = [
    "LocalAIMessage",
    "LocalChatModel",
    "LocalModelConfig",
    "LocalModelError",
    "LocalStructuredChatModel",
    "OpenAICompatibleChatModel",
    "default_local_command",
    "make_chat_model",
    "make_structured_llm",
]
