from demo.services.orchestrator import CLIOrchestrator


def test_edit_files_uses_claude_code_sdk_options(tmp_path, monkeypatch):
    (tmp_path / "train.py").write_text("x = 1")
    orch = CLIOrchestrator(workdir=tmp_path)
    seen: dict = {}

    def fake_run(prompt, option_kwargs, timeout_s):
        seen["prompt"] = prompt
        seen["option_kwargs"] = option_kwargs
        seen["timeout_s"] = timeout_s
        return "edited"

    monkeypatch.setattr("demo.services.orchestrator._run_claude_code", fake_run)

    result = orch.edit_files(prompt="change x to 2", editable=["train.py"])

    assert result["generator"] == "claude-code-sdk"
    assert result["stdout"] == "edited"
    assert "You may only edit these files: train.py" in seen["prompt"]
    assert seen["option_kwargs"]["cwd"] == tmp_path
    assert seen["option_kwargs"]["allowed_tools"] == ["Read", "Write"]
    assert seen["option_kwargs"]["permission_mode"] == "acceptEdits"
    assert seen["option_kwargs"]["max_turns"] == 5
    assert seen["timeout_s"] == 120


def test_draft_program_md_returns_sdk_generator(tmp_path, monkeypatch):
    orch = CLIOrchestrator(workdir=tmp_path)
    seen: dict = {}

    def fake_run(prompt, option_kwargs, timeout_s):
        seen["prompt"] = prompt
        seen["option_kwargs"] = option_kwargs
        seen["timeout_s"] = timeout_s
        return "drafted program"

    monkeypatch.setattr("demo.services.orchestrator._run_claude_code", fake_run)

    drafted, generator = orch.draft_program_md({"task_goal": "walk"})

    assert drafted == "drafted program"
    assert generator == "claude-code-sdk"
    assert '"task_goal": "walk"' in seen["prompt"]
    assert seen["option_kwargs"]["cwd"] == tmp_path
    assert seen["option_kwargs"]["allowed_tools"] == ["Read"]
    assert seen["option_kwargs"]["permission_mode"] == "plan"
    assert seen["option_kwargs"]["max_turns"] == 3
    assert seen["timeout_s"] == 60
