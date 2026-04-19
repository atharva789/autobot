"""Tests for recursive component IR and deterministic expansion."""
from __future__ import annotations

import pytest

from packages.pipeline.component_ir import (
    RobotComponentGraph,
    SubsystemSpec,
    AssemblySpec,
    ComponentSpec,
    PartSpec,
    PartGeometry,
    make_id,
    parent_id_from,
)
from packages.pipeline.component_expander import expand_candidate_to_component_graph
from packages.pipeline.schemas import RobotDesignCandidate


def _make_test_candidate(
    candidate_id: str = "A",
    embodiment_class: str = "quadruped",
    num_legs: int = 4,
    num_arms: int = 0,
    leg_dof: int = 3,
    arm_dof: int = 0,
) -> RobotDesignCandidate:
    return RobotDesignCandidate(
        candidate_id=candidate_id,
        embodiment_class=embodiment_class,
        num_legs=num_legs,
        num_arms=num_arms,
        has_torso=True,
        torso_length_m=0.3,
        arm_length_m=0.4,
        leg_length_m=0.35,
        arm_dof=arm_dof,
        leg_dof=leg_dof,
        spine_dof=0,
        actuator_class="servo",
        actuator_torque_nm=4.0,
        total_mass_kg=5.0,
        payload_capacity_kg=2.0,
        sensor_package=["imu", "camera"],
        rationale="Test candidate",
        confidence=0.9,
    )


class TestMakeId:
    def test_make_id_single_segment(self):
        result = make_id("subsystem", "locomotion")
        assert result == "subsystem:locomotion"

    def test_make_id_multiple_segments(self):
        result = make_id("component", "locomotion", "leg_fl", "hip")
        assert result == "component:locomotion.leg_fl.hip"

    def test_make_id_part_level(self):
        result = make_id("part", "locomotion", "leg_fl", "hip", "motor")
        assert result == "part:locomotion.leg_fl.hip.motor"

    def test_make_id_empty_segments_raises(self):
        with pytest.raises(ValueError):
            make_id("subsystem")


class TestParentIdFrom:
    def test_parent_of_component(self):
        result = parent_id_from("component:locomotion.leg_fl.hip")
        assert result == "assembly:locomotion.leg_fl"

    def test_parent_of_assembly(self):
        result = parent_id_from("assembly:locomotion.leg_fl")
        assert result == "subsystem:locomotion"

    def test_parent_of_subsystem_is_none(self):
        result = parent_id_from("subsystem:locomotion")
        assert result is None


class TestPartSpec:
    def test_part_spec_with_geometry(self):
        part = PartSpec(
            id="part:test.motor",
            parent_id="component:test",
            kind="actuator",
            role="motor",
            display_name="Test Motor",
            mass_kg=0.15,
            geometry=PartGeometry(
                primitive="cylinder",
                dimensions=(0.04, 0.03, 0.04),
                material_key="anodized_metal",
            ),
        )
        assert part.id == "part:test.motor"
        assert part.kind == "actuator"
        assert part.geometry is not None
        assert part.geometry.primitive == "cylinder"

    def test_part_spec_with_vendor(self):
        part = PartSpec(
            id="part:test.servo",
            parent_id="component:test",
            kind="actuator",
            role="servo",
            display_name="Dynamixel XM430",
            vendor="robotis",
            sku="XM430-W350-R",
            unit_price_usd=269.90,
        )
        assert part.vendor == "robotis"
        assert part.sku == "XM430-W350-R"
        assert part.unit_price_usd == 269.90


class TestComponentSpec:
    def test_component_with_parts(self):
        comp = ComponentSpec(
            id="component:test.hip",
            parent_id="assembly:test.leg",
            kind="joint_module",
            display_name="Hip Joint",
            is_actuated=True,
            dof=1,
            parts=[
                PartSpec(
                    id="part:test.hip.motor",
                    parent_id="component:test.hip",
                    kind="actuator",
                    role="motor",
                    display_name="motor",
                    mass_kg=0.15,
                ),
                PartSpec(
                    id="part:test.hip.encoder",
                    parent_id="component:test.hip",
                    kind="encoder",
                    role="encoder",
                    display_name="encoder",
                    mass_kg=0.02,
                ),
            ],
        )
        assert len(comp.parts) == 2
        assert comp.part_ids() == ["part:test.hip.motor", "part:test.hip.encoder"]
        assert comp.total_mass_kg() == pytest.approx(0.17, rel=0.01)


class TestAssemblySpec:
    def test_assembly_with_components(self):
        asm = AssemblySpec(
            id="assembly:locomotion.leg_fl",
            parent_id="subsystem:locomotion",
            kind="leg",
            display_name="Front Left Leg",
            template_key="leg_3dof",
            components=[
                ComponentSpec(
                    id="component:locomotion.leg_fl.hip",
                    parent_id="assembly:locomotion.leg_fl",
                    kind="joint_module",
                    display_name="Hip",
                    is_actuated=True,
                    dof=1,
                    parts=[
                        PartSpec(
                            id="part:locomotion.leg_fl.hip.motor",
                            parent_id="component:locomotion.leg_fl.hip",
                            kind="actuator",
                            role="motor",
                            display_name="motor",
                            mass_kg=0.15,
                            unit_price_usd=50.0,
                        ),
                    ],
                ),
            ],
            joints=[],
        )
        assert len(asm.components) == 1
        assert asm.all_parts() == asm.components[0].parts
        assert asm.total_mass_kg() == pytest.approx(0.15, rel=0.01)
        assert asm.total_cost_usd() == pytest.approx(50.0, rel=0.01)


class TestExpandCandidateToComponentGraph:
    def test_expand_quadruped_has_four_legs(self):
        candidate = _make_test_candidate(num_legs=4, leg_dof=3)
        graph = expand_candidate_to_component_graph(candidate)

        assert graph.candidate_id == "A"
        assert graph.embodiment_class == "quadruped"

        loco_subsystem = next((s for s in graph.subsystems if s.kind == "locomotion"), None)
        assert loco_subsystem is not None
        assert len(loco_subsystem.assemblies) == 4

        leg_names = {a.display_name for a in loco_subsystem.assemblies}
        assert "Leg Fl" in leg_names
        assert "Leg Fr" in leg_names
        assert "Leg Rl" in leg_names
        assert "Leg Rr" in leg_names

    def test_expand_quadruped_leg_has_components(self):
        candidate = _make_test_candidate(num_legs=4, leg_dof=3)
        graph = expand_candidate_to_component_graph(candidate)

        loco_subsystem = next(s for s in graph.subsystems if s.kind == "locomotion")
        leg = loco_subsystem.assemblies[0]

        assert len(leg.components) >= 4

        component_kinds = {c.kind for c in leg.components}
        assert "joint_module" in component_kinds
        assert "link" in component_kinds
        assert "end_effector" in component_kinds

    def test_expand_quadruped_joint_has_parts(self):
        candidate = _make_test_candidate(num_legs=4, leg_dof=3)
        graph = expand_candidate_to_component_graph(candidate)

        loco_subsystem = next(s for s in graph.subsystems if s.kind == "locomotion")
        leg = loco_subsystem.assemblies[0]
        hip = next(c for c in leg.components if "hip" in c.id)

        part_kinds = {p.kind for p in hip.parts}
        assert "actuator" in part_kinds
        assert "transmission" in part_kinds or len(hip.parts) >= 3
        assert "encoder" in part_kinds

    def test_expand_with_arms(self):
        candidate = _make_test_candidate(num_legs=0, num_arms=2, arm_dof=6)
        graph = expand_candidate_to_component_graph(candidate)

        manip_subsystem = next((s for s in graph.subsystems if s.kind == "manipulation"), None)
        assert manip_subsystem is not None
        assert len(manip_subsystem.assemblies) == 2

    def test_expand_with_torso(self):
        candidate = _make_test_candidate()
        graph = expand_candidate_to_component_graph(candidate)

        struct_subsystem = next((s for s in graph.subsystems if s.kind == "structure"), None)
        assert struct_subsystem is not None

        torso = next((a for a in struct_subsystem.assemblies if a.kind == "torso"), None)
        assert torso is not None

        component_kinds = {c.kind for c in torso.components}
        assert "chassis" in component_kinds

    def test_expand_with_sensors_creates_head(self):
        candidate = _make_test_candidate()
        graph = expand_candidate_to_component_graph(candidate)

        sensing_subsystem = next((s for s in graph.subsystems if s.kind == "sensing"), None)
        assert sensing_subsystem is not None

        head = next((a for a in sensing_subsystem.assemblies if a.kind == "head"), None)
        assert head is not None

    def test_expand_all_ids_are_hierarchical(self):
        candidate = _make_test_candidate()
        graph = expand_candidate_to_component_graph(candidate)

        for subsystem in graph.subsystems:
            assert subsystem.id.startswith("subsystem:")
            for assembly in subsystem.assemblies:
                assert assembly.id.startswith("assembly:")
                assert assembly.parent_id == subsystem.id
                for component in assembly.components:
                    assert component.id.startswith("component:")
                    assert component.parent_id == assembly.id
                    for part in component.parts:
                        assert part.id.startswith("part:")
                        assert part.parent_id == component.id

    def test_expand_to_flat_node_list(self):
        candidate = _make_test_candidate()
        graph = expand_candidate_to_component_graph(candidate)
        nodes = graph.to_flat_node_list()

        assert len(nodes) > 0

        levels = {n["level"] for n in nodes}
        assert "subsystem" in levels
        assert "assembly" in levels
        assert "component" in levels
        assert "part" in levels

        for node in nodes:
            assert "id" in node
            assert "parent_id" in node
            assert "display_name" in node

    def test_expand_has_nonzero_dof(self):
        candidate = _make_test_candidate(num_legs=4, leg_dof=3, num_arms=2, arm_dof=6)
        graph = expand_candidate_to_component_graph(candidate)

        assert graph.total_dof() > 0

    def test_expand_biped(self):
        candidate = _make_test_candidate(embodiment_class="biped", num_legs=2, leg_dof=6)
        graph = expand_candidate_to_component_graph(candidate)

        loco_subsystem = next(s for s in graph.subsystems if s.kind == "locomotion")
        assert len(loco_subsystem.assemblies) == 2

    def test_expand_mobile_arm(self):
        candidate = _make_test_candidate(
            embodiment_class="mobile_arm",
            num_legs=0,
            num_arms=1,
            arm_dof=6,
        )
        graph = expand_candidate_to_component_graph(candidate)

        manip_subsystem = next((s for s in graph.subsystems if s.kind == "manipulation"), None)
        assert manip_subsystem is not None
        assert len(manip_subsystem.assemblies) == 1


class TestRobotComponentGraph:
    def test_find_by_id_subsystem(self):
        candidate = _make_test_candidate()
        graph = expand_candidate_to_component_graph(candidate)

        found = graph.find_by_id("subsystem:locomotion")
        assert found is not None
        assert isinstance(found, SubsystemSpec)
        assert found.kind == "locomotion"

    def test_find_by_id_assembly(self):
        candidate = _make_test_candidate()
        graph = expand_candidate_to_component_graph(candidate)

        loco = next(s for s in graph.subsystems if s.kind == "locomotion")
        leg_id = loco.assemblies[0].id

        found = graph.find_by_id(leg_id)
        assert found is not None
        assert isinstance(found, AssemblySpec)

    def test_find_by_id_part(self):
        candidate = _make_test_candidate()
        graph = expand_candidate_to_component_graph(candidate)

        all_parts = graph.all_parts()
        assert len(all_parts) > 0

        first_part = all_parts[0]
        found = graph.find_by_id(first_part.id)
        assert found is not None
        assert isinstance(found, PartSpec)
        assert found.id == first_part.id

    def test_total_mass_is_sum_of_parts(self):
        candidate = _make_test_candidate()
        graph = expand_candidate_to_component_graph(candidate)

        total = graph.total_mass_kg()
        sum_parts = sum(p.mass_kg or 0.0 for p in graph.all_parts())

        assert total == pytest.approx(sum_parts, rel=0.01)
