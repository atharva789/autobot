from demo.services.orchestrator import GeminiOrchestrator


def test_edit_files_uses_gemini(tmp_path, monkeypatch):
    (tmp_path / "train.py").write_text("x = 1")
    orch = GeminiOrchestrator(workdir=tmp_path)
    seen: dict = {}

    def fake_gemini_prompt(prompt, system_prompt, timeout_s=120):
        seen["prompt"] = prompt
        seen["system_prompt"] = system_prompt
        seen["timeout_s"] = timeout_s
        return "edited"

    monkeypatch.setattr("demo.services.orchestrator._run_gemini_prompt", fake_gemini_prompt)

    result = orch.edit_files(prompt="change x to 2", editable=["train.py"])

    assert result["generator"] == "gemini"
    assert result["stdout"] == "edited"
    assert "change x to 2" in seen["prompt"]
    assert "x = 1" in seen["prompt"]
    assert "robot research" in seen["system_prompt"].lower()


def test_draft_program_md_returns_gemini_generator(tmp_path, monkeypatch):
    orch = GeminiOrchestrator(workdir=tmp_path)
    seen: dict = {}

    def fake_gemini_prompt(prompt, system_prompt, timeout_s=120):
        seen["prompt"] = prompt
        seen["system_prompt"] = system_prompt
        seen["timeout_s"] = timeout_s
        return "drafted program"

    monkeypatch.setattr("demo.services.orchestrator._run_gemini_prompt", fake_gemini_prompt)

    drafted, generator = orch.draft_program_md({"task_goal": "walk"})

    assert drafted == "drafted program"
    assert generator == "gemini"
    assert '"task_goal": "walk"' in seen["prompt"]
    assert "research" in seen["system_prompt"].lower()
