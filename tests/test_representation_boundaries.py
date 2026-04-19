"""
Tests for Phase 0: Clean representation boundaries.

Acceptance criteria:
- No file called URDF emits MJCF.
- Concept rendering is clearly separated from compiled artifact rendering.
- All simulator outputs are clearly labeled as placeholders or canonical.
"""

import pytest
import re
from pathlib import Path


class TestNamingConventions:
    """Files must be named according to their actual output format."""

    def test_no_urdf_file_emits_mujoco_xml(self):
        """Files with 'urdf' in name must not emit <mujoco> tags."""
        pipeline_dir = Path(__file__).parent.parent / "packages" / "pipeline"
        urdf_files = list(pipeline_dir.glob("*urdf*.py"))

        violations = []
        for filepath in urdf_files:
            content = filepath.read_text()
            if "<mujoco" in content or "'<mujoco" in content or '"<mujoco' in content:
                violations.append(filepath.name)

        assert not violations, (
            f"Files with 'urdf' in name emit MJCF format: {violations}. "
            "Rename to mjcf_* or change output format."
        )

    def test_mjcf_files_emit_mujoco_xml(self):
        """Files with 'mjcf' in name should emit <mujoco> tags."""
        pipeline_dir = Path(__file__).parent.parent / "packages" / "pipeline"
        mjcf_files = list(pipeline_dir.glob("*mjcf*.py"))

        for filepath in mjcf_files:
            content = filepath.read_text()
            assert "<mujoco" in content or "mujoco" in content.lower(), (
                f"{filepath.name} is labeled MJCF but doesn't reference MuJoCo format"
            )


class TestModuleDocumentation:
    """Modules must clearly document their purpose and output type."""

    def test_mjx_screener_documents_placeholder_status(self):
        """mjx_screener.py must document it produces placeholder geometry."""
        screener_path = Path(__file__).parent.parent / "packages" / "pipeline" / "mjx_screener.py"
        content = screener_path.read_text()

        has_placeholder_doc = any(term in content.lower() for term in [
            "placeholder", "screening", "approximate", "simplified"
        ])
        assert has_placeholder_doc, (
            "mjx_screener.py must document that it produces placeholder/screening geometry, "
            "not canonical robot descriptions"
        )

    def test_design_generator_is_proposal_only(self):
        """design_generator.py should not directly emit simulator artifacts."""
        generator_path = Path(__file__).parent.parent / "packages" / "pipeline" / "design_generator.py"
        content = generator_path.read_text()

        # Should not contain direct URDF/MJCF generation
        direct_export = re.search(r'def\s+generate_urdf|def\s+generate_mjcf|def\s+export_', content)
        assert not direct_export, (
            f"design_generator.py should only propose designs, not directly generate exports. "
            f"Found: {direct_export.group() if direct_export else 'N/A'}"
        )


class TestIRExistence:
    """Phase 1 prep: Verify IR module structure exists."""

    def test_ir_package_exists(self):
        """packages/pipeline/ir/ directory should exist for canonical IR."""
        ir_dir = Path(__file__).parent.parent / "packages" / "pipeline" / "ir"
        assert ir_dir.exists(), (
            "packages/pipeline/ir/ must exist for canonical intermediate representation"
        )

    def test_ir_has_design_ir_module(self):
        """IR package should have design_ir.py for RobotDesignIR."""
        design_ir = Path(__file__).parent.parent / "packages" / "pipeline" / "ir" / "design_ir.py"
        assert design_ir.exists(), (
            "packages/pipeline/ir/design_ir.py must exist for RobotDesignIR"
        )


class TestCompilerExistence:
    """Phase 2 prep: Verify compiler structure exists."""

    def test_compilers_package_exists(self):
        """packages/pipeline/compilers/ should exist for standards compilers."""
        compilers_dir = Path(__file__).parent.parent / "packages" / "pipeline" / "compilers"
        assert compilers_dir.exists(), (
            "packages/pipeline/compilers/ must exist for URDF/MJCF compilers"
        )

    def test_mjcf_compiler_exists(self):
        """MJCF compiler should exist and be separate from screener."""
        mjcf_compiler = Path(__file__).parent.parent / "packages" / "pipeline" / "compilers" / "mjcf_compiler.py"
        assert mjcf_compiler.exists(), (
            "packages/pipeline/compilers/mjcf_compiler.py must exist for canonical MJCF output"
        )
