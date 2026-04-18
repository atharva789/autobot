from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
from typing import Any


DEFAULT_CLAUDE_CODE_MODEL = "claude-sonnet-4-20250514"


async def _stream_claude_code(
    prompt: str,
    option_kwargs: dict[str, Any],
    timeout_s: int,
) -> str:
    try:
        from claude_code_sdk import ClaudeCodeOptions, query
    except ImportError as exc:
        raise RuntimeError(
            "Claude Code SDK is not installed. Install `claude-code-sdk` in Python "
            "and `@anthropic-ai/claude-code` with npm."
        ) from exc

    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise RuntimeError(
            "ANTHROPIC_API_KEY must be set to use the Claude Code SDK."
        )

    options = ClaudeCodeOptions(**option_kwargs)

    async def _collect() -> str:
        fallback_parts: list[str] = []
        final_result: str | None = None

        async for message in query(prompt=prompt, options=options):
            result = getattr(message, "result", None)
            if isinstance(result, str) and result.strip():
                final_result = result.strip()

            content = getattr(message, "content", None)
            if not content:
                continue

            for block in content:
                text = getattr(block, "text", None)
                if isinstance(text, str) and text:
                    fallback_parts.append(text)

        if final_result:
            return final_result

        combined = "".join(fallback_parts).strip()
        if combined:
            return combined

        raise RuntimeError("Claude Code SDK returned no text result.")

    try:
        return await asyncio.wait_for(_collect(), timeout=timeout_s)
    except asyncio.TimeoutError as exc:
        raise RuntimeError(
            f"Claude Code SDK timed out after {timeout_s}s."
        ) from exc
    except RuntimeError:
        raise
    except Exception as exc:
        raise RuntimeError(f"Claude Code SDK failed: {exc}") from exc


def _run_claude_code(
    prompt: str,
    option_kwargs: dict[str, Any],
    timeout_s: int,
) -> str:
    return asyncio.run(_stream_claude_code(prompt, option_kwargs, timeout_s))


def resolve_claude_code_model() -> str:
    return os.environ.get("CLAUDE_CODE_MODEL", DEFAULT_CLAUDE_CODE_MODEL)


class CLIOrchestrator:
    def __init__(self, workdir: Path) -> None:
        self.workdir = Path(workdir)

    def _run_prompt(
        self,
        *,
        prompt: str,
        system_prompt: str,
        allowed_tools: list[str],
        permission_mode: str,
        max_turns: int,
        timeout_s: int,
    ) -> str:
        option_kwargs = {
            "cwd": self.workdir,
            "system_prompt": system_prompt,
            "allowed_tools": allowed_tools,
            "permission_mode": permission_mode,
            "max_turns": max_turns,
            "model": resolve_claude_code_model(),
        }
        return _run_claude_code(prompt, option_kwargs, timeout_s)

    def edit_files(
        self, prompt: str, editable: list[str], timeout_s: int = 120
    ) -> dict:
        file_list = " ".join(editable)
        full_prompt = (
            f"{prompt}\n\n"
            f"You may only edit these files: {file_list}\n"
            "Do not use Bash. Read files before editing when needed."
        )
        stdout = self._run_prompt(
            prompt=full_prompt,
            system_prompt=(
                "You are an autonomous robot research coding agent. "
                "Make focused changes only to the allowed files."
            ),
            allowed_tools=["Read", "Write"],
            permission_mode="acceptEdits",
            max_turns=5,
            timeout_s=timeout_s,
        )
        return {"generator": "claude-code-sdk", "stdout": stdout}

    def draft_program_md(
        self, er16_plan: dict, timeout_s: int = 60
    ) -> tuple[str, str]:
        prompt = (
            "Draft a program.md file (research agenda) for this task:\n"
            f"{json.dumps(er16_plan, indent=2)}\n\n"
            "The program.md should describe:\n"
            "1. What morphology features to explore\n"
            "2. What controller changes to try\n"
            "3. How to measure progress\n"
            "4. What to avoid (known failure modes)\n"
            "Keep it under 300 words. Plain English."
        )
        stdout = self._run_prompt(
            prompt=prompt,
            system_prompt=(
                "You are setting up an autonomous robot design research loop. "
                "Draft concise, practical research agendas."
            ),
            allowed_tools=["Read"],
            permission_mode="plan",
            max_turns=3,
            timeout_s=timeout_s,
        )
        return stdout.strip(), "claude-code-sdk"
