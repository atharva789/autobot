from __future__ import annotations
import json
import subprocess
from pathlib import Path


class CLIOrchestrator:
    def __init__(self, workdir: Path) -> None:
        self.workdir = Path(workdir)

    def edit_files(
        self, prompt: str, editable: list[str], timeout_s: int = 120
    ) -> dict:
        file_list = " ".join(editable)
        full_prompt = f"{prompt}\n\nYou may only edit these files: {file_list}"
        result = subprocess.run(
            ["codex", "exec", full_prompt],
            cwd=self.workdir,
            capture_output=True,
            text=True,
            timeout=timeout_s,
        )
        if result.returncode == 0:
            return {"generator": "codex", "stdout": result.stdout}
        result = subprocess.run(
            ["claude", "-p", full_prompt, "--allowedTools", "Edit,Read"],
            cwd=self.workdir,
            capture_output=True,
            text=True,
            timeout=timeout_s,
        )
        if result.returncode != 0:
            raise RuntimeError(
                f"Both Codex and Claude CLI failed.\nClaude stderr: {result.stderr}"
            )
        return {"generator": "claude-code", "stdout": result.stdout}

    def draft_program_md(
        self, er16_plan: dict, timeout_s: int = 60
    ) -> tuple[str, str]:
        prompt = (
            "You are setting up an autonomous robot design research loop.\n"
            "Draft a program.md file (research agenda) for this task:\n"
            f"{json.dumps(er16_plan, indent=2)}\n\n"
            "The program.md should describe:\n"
            "1. What morphology features to explore\n"
            "2. What controller changes to try\n"
            "3. How to measure progress\n"
            "4. What to avoid (known failure modes)\n"
            "Keep it under 300 words. Plain English."
        )
        result = subprocess.run(
            ["codex", "exec", prompt],
            cwd=self.workdir,
            capture_output=True,
            text=True,
            timeout=timeout_s,
        )
        if result.returncode == 0:
            return result.stdout.strip(), "codex"
        result = subprocess.run(
            ["claude", "-p", prompt],
            cwd=self.workdir,
            capture_output=True,
            text=True,
            timeout=timeout_s,
        )
        return result.stdout.strip(), "claude-code"
