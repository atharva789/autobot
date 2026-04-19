from __future__ import annotations

import json
import os
from pathlib import Path


DEFAULT_GEMINI_MODEL = "gemini-2.5-pro"


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

    response = client.models.generate_content(
        model=model,
        contents=prompt,
        config=config,
    )

    if not response.text:
        raise RuntimeError("Gemini returned no text response.")

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

        stdout = _run_gemini_prompt(
            prompt=full_prompt,
            system_prompt=(
                "You are an autonomous robot research coding agent. "
                "Make focused changes to improve the robot design code."
            ),
            timeout_s=timeout_s,
        )

        return {"generator": "gemini", "stdout": stdout}

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
        stdout = _run_gemini_prompt(
            prompt=prompt,
            system_prompt=(
                "You are setting up an autonomous robot design research loop. "
                "Draft concise, practical research agendas."
            ),
            timeout_s=timeout_s,
        )
        return stdout.strip(), "gemini"


CLIOrchestrator = GeminiOrchestrator
