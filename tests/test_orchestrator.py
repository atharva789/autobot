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


def test_draft_program_md_falls_back_when_gemini_is_unavailable(tmp_path, monkeypatch):
    orch = GeminiOrchestrator(workdir=tmp_path)

    def fake_gemini_prompt(prompt, system_prompt, timeout_s=120):
        raise RuntimeError("temporary provider outage")

    monkeypatch.setattr("demo.services.orchestrator._run_gemini_prompt", fake_gemini_prompt)

    drafted, generator = orch.draft_program_md({"task_goal": "climb a wall", "search_queries": ["wall climb side view"]})

    assert generator == "fallback"
    assert "# Program: climb a wall" in drafted
    assert "wall climb side view" in drafted
    assert "temporary provider outage" in drafted


def test_edit_files_falls_back_to_noop_when_gemini_is_unavailable(tmp_path, monkeypatch):
    (tmp_path / "train.py").write_text("x = 1")
    orch = GeminiOrchestrator(workdir=tmp_path)

    def fake_gemini_prompt(prompt, system_prompt, timeout_s=120):
        raise RuntimeError("temporary provider outage")

    monkeypatch.setattr("demo.services.orchestrator._run_gemini_prompt", fake_gemini_prompt)

    result = orch.edit_files(prompt="change x to 2", editable=["train.py"])

    assert result["generator"] == "fallback"
    assert result["stdout"] == ""
    assert "reusing current files" in result["warning"].lower()


def test_apply_edit_output_updates_multiple_files(tmp_path):
    (tmp_path / "train.py").write_text("x = 1\n")
    (tmp_path / "morphology_factory.py").write_text("y = 1\n")
    orch = GeminiOrchestrator(workdir=tmp_path)

    updated = orch.apply_edit_output(
        "=== train.py ===\n"
        "x = 2\n"
        "=== morphology_factory.py ===\n"
        "y = 3\n",
        ["train.py", "morphology_factory.py"],
    )

    assert updated == ["train.py", "morphology_factory.py"]
    assert (tmp_path / "train.py").read_text() == "x = 2\n"
    assert (tmp_path / "morphology_factory.py").read_text() == "y = 3\n"


def test_apply_edit_output_single_file_fallback(tmp_path):
    (tmp_path / "train.py").write_text("x = 1\n")
    orch = GeminiOrchestrator(workdir=tmp_path)

    updated = orch.apply_edit_output("x = 4", ["train.py"])

    assert updated == ["train.py"]
    assert (tmp_path / "train.py").read_text() == "x = 4\n"
