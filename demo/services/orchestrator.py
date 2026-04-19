from __future__ import annotations

import json
import os
import re
from pathlib import Path


DEFAULT_GEMINI_MODEL = "gemini-2.5-pro"


def build_fallback_program_md(er16_plan: dict, reason: str | None = None) -> str:
    task_goal = str(er16_plan.get("task_goal") or "robot task").strip()
    affordances = er16_plan.get("affordances") or []
    success = str(er16_plan.get("success_criteria") or "demonstrate reliable task completion").strip()
    queries = er16_plan.get("search_queries") or []
    lines = [
        f"# Program: {task_goal}",
        "",
        "## Morphology focus",
        f"- Prioritize geometry and actuation that directly support: {task_goal}.",
        f"- Preserve or strengthen these affordances: {', '.join(map(str, affordances)) if affordances else 'task-relevant contact, reach, and stability'}.",
        "",
        "## Controller focus",
        "- Improve stability, contact confidence, and payload retention before chasing novelty.",
        "- Prefer conservative edits that keep exported artifacts valid.",
        "",
        "## Evaluation",
        f"- Success criteria: {success}.",
        f"- Reference searches to preserve: {', '.join(map(str, queries[:3])) if queries else 'existing task references'}.",
        "",
        "## Avoid",
        "- Regressing task fit for generic morphology changes.",
        "- Breaking exports, render artifacts, or procurement grounding.",
    ]
    if reason:
        lines.extend(["", f"_Fallback draft generated because the model path was unavailable: {reason}_"])
    return "\n".join(lines)


def _get_gemini_client():
    from google import genai
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY must be set for orchestrator.")
    return genai.Client(api_key=api_key)


def _run_gemini_prompt(
    prompt: str,
    system_prompt: str,
    timeout_s: int = 120,
) -> str:
    from google.genai import types as genai_types

    client = _get_gemini_client()
    model = os.environ.get("GEMINI_MODEL", DEFAULT_GEMINI_MODEL)

    config = genai_types.GenerateContentConfig(
        system_instruction=system_prompt,
        temperature=0.7,
        max_output_tokens=4096,
        http_options={"timeout": timeout_s * 1000},
    )

    try:
        response = client.models.generate_content(
            model=model,
            contents=prompt,
            config=config,
        )
    except Exception as e:
        raise RuntimeError(f"Gemini API call failed: {e}") from e

    if not response.text:
        candidates = getattr(response, "candidates", [])
        if candidates:
            first = candidates[0]
            finish_reason = getattr(first, "finish_reason", None)
            safety_ratings = getattr(first, "safety_ratings", [])
            raise RuntimeError(
                f"Gemini returned no text. finish_reason={finish_reason}, "
                f"safety_ratings={safety_ratings}"
            )
        raise RuntimeError("Gemini returned no text response and no candidates.")

    return response.text.strip()


class GeminiOrchestrator:
    def __init__(self, workdir: Path) -> None:
        self.workdir = Path(workdir)

    def edit_files(
        self, prompt: str, editable: list[str], timeout_s: int = 120
    ) -> dict:
        file_contents: dict[str, str] = {}
        for fpath in editable:
            full_path = self.workdir / fpath
            if full_path.exists():
                file_contents[fpath] = full_path.read_text()

        context = "\n\n".join(
            f"=== {fp} ===\n{content}" for fp, content in file_contents.items()
        )

        full_prompt = (
            f"{prompt}\n\n"
            f"Current file contents:\n{context}\n\n"
            "Return ONLY the updated code for each file that needs changes. "
            "Use the format:\n"
            "=== path/to/file.py ===\n<full updated content>\n\n"
            "Do NOT include explanation, just the file contents."
        )

        try:
            stdout = _run_gemini_prompt(
                prompt=full_prompt,
                system_prompt=(
                    "You are an autonomous robot research coding agent. "
                    "Make focused changes to improve the robot design code."
                ),
                timeout_s=timeout_s,
            )
            return {"generator": "gemini", "stdout": stdout}
        except Exception as exc:
            return {
                "generator": "fallback",
                "stdout": "",
                "warning": f"Gemini edit step unavailable; reusing current files. reason={exc}",
            }

    def apply_edit_output(self, stdout: str, editable: list[str]) -> list[str]:
        editable_set = {str(path) for path in editable}
        updated: list[str] = []
        current_path: str | None = None
        buffer: list[str] = []
        parsed_any = False

        def flush() -> None:
            nonlocal current_path, buffer, updated
            if current_path is None:
                buffer = []
                return
            body = "".join(buffer).lstrip("\n")
            if current_path in editable_set and body:
                target = self.workdir / current_path
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(body)
                updated.append(current_path)
            buffer = []

        for line in stdout.splitlines(keepends=True):
            match = re.match(r"^===\s+(.+?)\s+===\s*$", line)
            if match:
                parsed_any = True
                flush()
                current_path = match.group(1).strip()
                continue
            buffer.append(line)
        flush()

        if parsed_any:
            return updated

        if len(editable) == 1 and stdout.strip():
            target = self.workdir / editable[0]
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(stdout.strip() + "\n")
            return [editable[0]]
        return []

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
        try:
            stdout = _run_gemini_prompt(
                prompt=prompt,
                system_prompt=(
                    "You are setting up an autonomous robot design research loop. "
                    "Draft concise, practical research agendas."
                ),
                timeout_s=timeout_s,
            )
            return stdout.strip(), "gemini"
        except Exception as exc:
            return build_fallback_program_md(er16_plan, str(exc)), "fallback"


CLIOrchestrator = GeminiOrchestrator
