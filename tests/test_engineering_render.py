from __future__ import annotations

import base64
import json
import subprocess
from pathlib import Path

from packages.pipeline.design_generator import build_render_payload
from packages.pipeline.schemas import RobotDesignCandidate, TaskSpec


REPO_ROOT = Path(__file__).resolve().parents[1]


def _sample_candidate() -> RobotDesignCandidate:
    return RobotDesignCandidate(
        candidate_id="A",
        embodiment_class="hybrid",
        num_legs=2,
        num_arms=2,
        has_torso=True,
        torso_length_m=0.46,
        arm_length_m=0.52,
        leg_length_m=0.6,
        arm_dof=5,
        leg_dof=4,
        spine_dof=2,
        actuator_class="bldc",
        actuator_torque_nm=24.0,
        total_mass_kg=18.0,
        payload_capacity_kg=4.0,
        sensor_package=["imu", "camera", "force", "encoder"],
        rationale="Lean hybrid climber with dual grasping limbs and centered payload support.",
        confidence=0.84,
    )


def test_render_payload_emits_engineering_scene_contract():
    payload = build_render_payload(_sample_candidate())

    assert payload["engineering_ready"] is True
    assert payload["ui_scene"]["render_mode"] == "engineering"
    assert payload["ui_scene"]["stats"]["mesh_node_count"] > 0
    assert payload["ui_scene"]["stats"]["joint_anchor_count"] > 0
    assert payload["ui_scene"]["stats"]["material_count"] >= 8
    assert payload["ui_scene"]["stats"]["panel_node_count"] >= 8
    assert payload["ui_scene"]["stats"]["head_node_count"] >= 8
    assert payload["ui_scene"]["stats"]["sensor_node_count"] >= 4
    assert payload["ui_scene"]["stats"]["head_profile"] in {"visor_sleek", "sensor_cluster", "aperture_guard"}
    assert payload["ui_scene"]["stats"]["pbr_extension_count"] >= 4
    assert payload["ui_scene"]["stats"]["visual_complexity_score"] >= 0.75
    assert any(node["component_kind"] == "structural" for node in payload["ui_scene"]["nodes"])


def test_render_payload_emits_component_metadata_for_hover_inspection():
    payload = build_render_payload(_sample_candidate())

    node = payload["ui_scene"]["nodes"][0]

    assert isinstance(node["component_id"], str) and node["component_id"]
    assert isinstance(node["structure_id"], str) and node["structure_id"]
    assert isinstance(node["display_name"], str) and node["display_name"]
    assert isinstance(node["material_label"], str) and node["material_label"]
    assert isinstance(node["focus_summary"], str) and node["focus_summary"]
    assert isinstance(node["bounds_m"], list) and len(node["bounds_m"]) == 3
    assert payload["ui_scene"]["stats"]["mesh_node_count"] >= 36
    names = {scene_node["name"] for scene_node in payload["ui_scene"]["nodes"]}
    assert "head_main_shell" in names
    assert "head_visor" in names
    assert "head_neck_yoke" in names


def test_render_payload_uses_task_conditioned_geometry_for_climbing_payload():
    payload = build_render_payload(
        _sample_candidate(),
        TaskSpec(
            task_goal="climb a near-vertical rock wall while carrying a rope pack",
            environment="outdoor",
            locomotion_type="walking",
            manipulation_required=True,
            payload_kg=4.0,
            success_criteria="ascend while keeping the pack stable",
            search_queries=["rock climber carrying rope pack", "vertical climbing side view"],
        ),
    )

    names = {node["name"] for node in payload["ui_scene"]["nodes"]}
    component_kinds = {node["component_kind"] for node in payload["ui_scene"]["nodes"]}

    assert payload["ui_scene"]["stats"]["task_geometry_profile"] == "climbing_payload"
    assert payload["ui_scene"]["stats"]["accessory_node_count"] >= 4
    assert "payload_pack" in names
    assert any(name.startswith("arm_1_gripper") for name in names)
    assert "torso_chest_plate" in names
    assert "torso_back_plate" in names
    assert "payload_strap_left" in names
    assert "head_visor" in names
    assert any(name.startswith("head_camera") or name.startswith("head_aperture") for name in names)
    assert "payload_module" in component_kinds
    assert "climbing_gripper" in component_kinds


def test_render_glb_is_parseable_by_gltfloader(tmp_path: Path):
    payload = build_render_payload(
        _sample_candidate(),
        TaskSpec(
            task_goal="descend a slippery slope carrying a rescue payload",
            environment="outdoor",
            locomotion_type="walking",
            manipulation_required=True,
            payload_kg=4.0,
            success_criteria="descend without slipping or dropping the load",
            search_queries=["slippery slope rescue descent", "carry payload downhill side view"],
        ),
    )
    data_url = payload["render_glb"]
    encoded = data_url.split(",", 1)[1]
    glb_path = tmp_path / "render.glb"
    glb_path.write_bytes(base64.b64decode(encoded))

    script = """
import fs from 'node:fs/promises';
import { GLTFLoader } from 'three/examples/jsm/loaders/GLTFLoader.js';

globalThis.self = globalThis;

const filePath = process.argv[1];
const data = await fs.readFile(filePath);
const buffer = data.buffer.slice(data.byteOffset, data.byteOffset + data.byteLength);
const loader = new GLTFLoader();
const gltf = await loader.parseAsync(buffer, '');

let meshCount = 0;
const nodeNames = [];
let meshesWithNormals = 0;
const materials = new Set();
gltf.scene.traverse((node) => {
  nodeNames.push(node.name);
  if (node.isMesh) {
    meshCount += 1;
    if (node.geometry?.attributes?.normal) meshesWithNormals += 1;
    if (node.material?.name) materials.add(node.material.name);
  }
});

console.log(JSON.stringify({ meshCount, meshesWithNormals, materialCount: materials.size, nodeNames }));
"""
    completed = subprocess.run(
        ["node", "--input-type=module", "-e", script, str(glb_path)],
        cwd=REPO_ROOT / "apps" / "web",
        capture_output=True,
        text=True,
        check=True,
    )
    parsed = json.loads(completed.stdout)
    assert parsed["meshCount"] >= 30
    assert parsed["meshesWithNormals"] == parsed["meshCount"]
    assert parsed["materialCount"] >= 8
    assert any(name == "payload_pack" for name in parsed["nodeNames"])
    assert any(name.startswith("leg_1_spike") for name in parsed["nodeNames"])
    assert "torso_chest_plate" in parsed["nodeNames"]
    assert "payload_strap_left" in parsed["nodeNames"]
    assert "head_main_shell" in parsed["nodeNames"]
    assert "head_visor" in parsed["nodeNames"]
    assert len(parsed["nodeNames"]) >= payload["ui_scene"]["stats"]["mesh_node_count"]
