from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
PAGE_FILE = REPO_ROOT / "apps" / "web" / "app" / "page.tsx"
GLOBAL_CSS = REPO_ROOT / "apps" / "web" / "app" / "globals.css"


def test_root_page_uses_simplified_robogrammar_generator():
    source = PAGE_FILE.read_text()

    assert "RoboGrammar Morphology Generator" in source
    assert "Generate Morphologies" in source
    assert "MorphologySketch" in source
    assert "GrammarPanel" in source
    assert "Structural Rules" in source
    assert "Evaluator Checklist" in source
    assert "Tasks" not in source
    assert "Export targets" not in source
    assert "Commit v3" not in source
    assert "Morphology Studio" not in source
    assert "Commitment zone" not in source
    assert "Synthesis stream" not in source


def test_root_page_only_uses_current_ingest_and_generate_routes():
    source = PAGE_FILE.read_text()

    assert "api.ingest.start" in source
    assert "api.designs.generate" in source
    assert "api.designs.getSpec" not in source
    assert "api.designs.getCheckpoints" not in source
    assert "api.designs.getTasks" not in source
    assert "api.designs.getExports" not in source
    assert "api.designs.decideCheckpoint" not in source
    assert "api.designs.runTask" not in source
    assert "api.designs.recordClip" not in source
    assert "api.designs.revise" not in source
    assert "EventSource" not in source
    assert "api.hitl.getSetup" not in source
    assert "api.hitl.saveSetup" not in source
    assert "readOnly" not in source


def test_workspace_theme_uses_squared_ide_tokens():
    css = GLOBAL_CSS.read_text()

    assert "color-scheme: dark;" in css
    assert "--radius-sm" in css
    assert ".autobot-shell" in css
    assert ".autobot-panel" in css


def test_root_page_renders_simple_svg_morphology_from_candidate_shape():
    page_source = PAGE_FILE.read_text()
    viewer_source = (REPO_ROOT / "apps" / "web" / "components" / "MorphologyViewer.tsx").read_text()

    assert "<svg viewBox" in page_source
    assert "candidate.num_legs" in page_source
    assert "candidate.num_arms" in page_source
    assert "candidate.spine_dof" in page_source
    assert "renderGlb={render?.render_glb ?? null}" not in page_source
    assert "uiScene={render?.ui_scene ?? null}" not in page_source
    assert "engineering mode unavailable" in viewer_source.lower()
    assert "GLTFLoader" in viewer_source
    assert "hoveredComponent" not in page_source


def test_root_page_has_no_legacy_photon_or_checkpoint_controls():
    source = PAGE_FILE.read_text()
    lowered = source.lower()

    assert "phone number" not in lowered
    assert "send review poll" not in lowered
    assert "consent" not in lowered
    assert "Approve" not in source
    assert 'role="button"' not in source
    assert 'aria-expanded={expanded}' not in source


def test_api_cors_allows_127_frontend_origin():
    source = (REPO_ROOT / "apps" / "api" / "app.py").read_text()

    assert "http://127.0.0.1:3000" in source
    assert "allow_origin_regex" in source


def test_evolution_page_reads_iterations_from_backend_not_supabase():
    source = (REPO_ROOT / "apps" / "web" / "app" / "evolutions" / "[evoId]" / "page.tsx").read_text()
    history_source = (REPO_ROOT / "apps" / "web" / "components" / "EvolutionHistory.tsx").read_text()

    assert "api.evolutions.listIterations" in source
    assert "supabase" not in source
    assert "supabase" not in history_source
    assert "iterations={iterations}" in source


def test_program_page_does_not_decode_search_param_twice():
    source = (REPO_ROOT / "apps" / "web" / "app" / "evolutions" / "[evoId]" / "program" / "page.tsx").read_text()

    assert 'searchParams.get("draft") ?? ""' in source
    assert "decodeURIComponent" not in source
