from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
PAGE_FILE = REPO_ROOT / "apps" / "web" / "app" / "page.tsx"
GLOBAL_CSS = REPO_ROOT / "apps" / "web" / "app" / "globals.css"


def test_workspace_uses_autobot_shell_and_not_old_morphology_copy():
    source = PAGE_FILE.read_text()

    assert "AutoBot" in source
    assert "Tasks" in source
    assert "Export targets" in source
    assert "Commit v3" in source
    assert "Approve" in source
    assert "Morphology Studio" not in source
    assert "Commitment zone" not in source
    assert "Synthesis stream" not in source


def test_workspace_reads_runtime_state_from_backend_routes():
    source = PAGE_FILE.read_text()

    assert "api.designs.getSpec" in source
    assert "api.designs.getCheckpoints" in source
    assert "api.designs.getTasks" in source
    assert "api.designs.getExports" in source
    assert "api.designs.decideCheckpoint" in source
    assert "api.designs.runTask" in source
    assert "api.designs.recordClip" in source
    assert "api.designs.revise" in source
    assert "EventSource" in source
    assert "/events?follow=true" in source
    assert "api.hitl.getSetup" in source
    assert "api.hitl.saveSetup" in source
    assert "readOnly" not in source
    assert "Thread key" in source
    assert "1/{tasks.length}" not in source


def test_workspace_theme_uses_squared_ide_tokens():
    css = GLOBAL_CSS.read_text()

    assert "color-scheme: dark;" in css
    assert "--radius-sm" in css
    assert ".autobot-shell" in css
    assert ".autobot-panel" in css


def test_workspace_and_viewer_support_engineering_mode_and_degraded_fallback():
    page_source = PAGE_FILE.read_text()
    viewer_source = (REPO_ROOT / "apps" / "web" / "components" / "MorphologyViewer.tsx").read_text()

    assert "engineering" in page_source
    assert 'useState<DetailViewMode>("engineering")' in page_source
    assert "renderGlb={render?.render_glb ?? null}" in page_source
    assert "uiScene={render?.ui_scene ?? null}" in page_source
    assert "engineering mode unavailable" in viewer_source.lower()
    assert "GLTFLoader" in viewer_source
    assert "hoveredComponent" in page_source
    assert "onHoverComponent" in viewer_source
    assert "\"components\"" in page_source


def test_workspace_exposes_photon_setup_copy():
    source = PAGE_FILE.read_text().lower()

    assert "phone number" in source
    assert "send review poll" in source
    assert "consent" in source
