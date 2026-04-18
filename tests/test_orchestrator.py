import subprocess
from unittest.mock import patch
from demo.services.orchestrator import CLIOrchestrator


def test_codex_fallback_to_claude_on_failure(tmp_path):
    (tmp_path / "train.py").write_text("x = 1")
    orch = CLIOrchestrator(workdir=tmp_path)
    with patch("subprocess.run") as mock_run:
        mock_run.side_effect = [
            subprocess.CompletedProcess(args=[], returncode=1, stdout="", stderr="codex not found"),
            subprocess.CompletedProcess(args=[], returncode=0, stdout="ok", stderr=""),
        ]
        result = orch.edit_files(prompt="change x to 2", editable=["train.py"])
    assert result["generator"] == "claude-code"
    assert mock_run.call_count == 2


def test_edit_files_success_codex(tmp_path):
    (tmp_path / "train.py").write_text("x = 1")
    orch = CLIOrchestrator(workdir=tmp_path)
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = subprocess.CompletedProcess(
            args=[], returncode=0, stdout="edited", stderr=""
        )
        result = orch.edit_files(prompt="change x to 2", editable=["train.py"])
    assert result["generator"] == "codex"
