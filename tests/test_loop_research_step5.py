"""Build-order step 5 tests (plan.md §7): "G2/G3 structural diff. Gate: separates control from
per-schema hand-written scaffolds."

Covers the diff formula itself (contracts/eval-contract.md), the four permutation classes G2
needs, tau's derivation and its failure mode, and the two gates built on top of both.
"""

from __future__ import annotations

import dataclasses

import mujoco
import pytest

from packages.research.loop_research.baselines import (
    DEV_A_SCHEMA,
    DEV_B_SCHEMA,
    build_dev_a_baseline,
    build_dev_b_baseline,
)
from packages.research.loop_research.permutations import (
    PermutationError,
    build_permutation,
    dof_removed,
    limits_altered,
    link_scaled,
    topology_swapped,
)
from packages.research.loop_research.scaffold import Provenance, RewardTerm, Termination, TrainingScaffold
from packages.research.loop_research.static_scaffold_loop import run_static_scaffold_loop
from packages.research.loop_research.structural_diff import (
    jaccard_distance,
    normalized_weight_distance,
    structural_diff,
    symbol_set,
    term_names,
    termination_causes,
)
from packages.research.loop_research.structural_gates import run_g2, run_g3
from packages.research.loop_research.tau import TauUndefinedError, derive_tau

ORIGINAL_XML = DEV_A_SCHEMA.read_text()


def _scaffold(**overrides) -> TrainingScaffold:
    fields = dict(
        scaffold_id="sc_x",
        schema_id="dev-a",
        schema_digest="sha256:x",
        task_text="t",
        reward_terms=(RewardTerm("a", 0.5, "1", ("const.c",), ""),),
        terminations=(Termination("done", "1", ("const.c",), "success"),),
        curriculum=(),
        randomization=(),
        provenance=Provenance(prompt_version="v1", model_id="m", model_tier="cheap", seed=1),
    )
    fields.update(overrides)
    return TrainingScaffold(**fields)


# --- structural_diff components -----------------------------------------------------------------


def test_jaccard_distance_identical_sets_is_zero():
    assert jaccard_distance(frozenset({"a", "b"}), frozenset({"a", "b"})) == 0.0


def test_jaccard_distance_both_empty_is_zero():
    assert jaccard_distance(frozenset(), frozenset()) == 0.0


def test_jaccard_distance_disjoint_sets_is_one():
    assert jaccard_distance(frozenset({"a"}), frozenset({"b"})) == 1.0


def test_jaccard_distance_partial_overlap():
    # {a, b} vs {b, c}: intersection {b}=1, union {a,b,c}=3 -> 1 - 1/3
    assert jaccard_distance(frozenset({"a", "b"}), frozenset({"b", "c"})) == pytest.approx(1 - 1 / 3)


def test_normalized_weight_distance_no_common_terms_is_one():
    a = _scaffold(reward_terms=(RewardTerm("x", 0.5, "1", (), ""),))
    b = _scaffold(reward_terms=(RewardTerm("y", 0.9, "1", (), ""),))
    assert normalized_weight_distance(a, b) == 1.0


def test_normalized_weight_distance_identical_weights_is_zero():
    a = _scaffold(reward_terms=(RewardTerm("x", 0.5, "1", (), ""),))
    b = _scaffold(reward_terms=(RewardTerm("x", 0.5, "1", (), ""),))
    assert normalized_weight_distance(a, b) == 0.0


def test_structural_diff_is_zero_for_identical_scaffold():
    a = _scaffold()
    assert structural_diff(a, a) == 0.0


def test_structural_diff_is_symmetric():
    a = build_dev_a_baseline()
    b = build_dev_b_baseline()
    assert structural_diff(a, b) == pytest.approx(structural_diff(b, a))


def test_structural_diff_bounded_zero_one():
    a = build_dev_a_baseline()
    b = build_dev_b_baseline()
    d = structural_diff(a, b)
    assert 0.0 <= d <= 1.0


def test_structural_diff_between_baselines_is_positive():
    """The two hand-written baselines share reward-term names/weights by design (baselines.py) but
    reference different touch sensors -- D must be > 0, not 0, or the whole calibration breaks."""

    d = structural_diff(build_dev_a_baseline(), build_dev_b_baseline())
    assert d > 0.0


def test_symbol_set_includes_reward_and_termination_symbols():
    scaffold = _scaffold(
        reward_terms=(RewardTerm("a", 1.0, "1", ("joint.x",), ""),),
        terminations=(Termination("d", "1", ("body.y",), "success"),),
    )
    assert symbol_set(scaffold) == frozenset({"joint.x", "body.y"})


def test_term_names_and_termination_causes():
    scaffold = _scaffold(
        reward_terms=(RewardTerm("a", 1.0, "1", (), ""), RewardTerm("b", 1.0, "1", (), "")),
        terminations=(Termination("d", "1", (), "drop"),),
    )
    assert term_names(scaffold) == frozenset({"a", "b"})
    assert termination_causes(scaffold) == frozenset({"drop"})


# --- permutations --------------------------------------------------------------------------------


def test_link_scaled_produces_loadable_mjcf_and_changes_geometry():
    mutant_xml = link_scaled(ORIGINAL_XML, factor=1.5)
    model = mujoco.MjModel.from_xml_string(mutant_xml)
    original_model = mujoco.MjModel.from_xml_string(ORIGINAL_XML)
    assert not (model.body_pos == original_model.body_pos).all()


def test_link_scaled_rejects_factor_outside_contract_band():
    with pytest.raises(PermutationError):
        link_scaled(ORIGINAL_XML, factor=3.0)
    with pytest.raises(PermutationError):
        link_scaled(ORIGINAL_XML, factor=1.0)


def test_limits_altered_tightens_every_joint_range_by_40_percent():
    mutant_xml = limits_altered(ORIGINAL_XML, factor=0.6)
    model = mujoco.MjModel.from_xml_string(mutant_xml)
    original_model = mujoco.MjModel.from_xml_string(ORIGINAL_XML)
    for i in range(model.njnt):
        lo, hi = model.jnt_range[i]
        orig_lo, orig_hi = original_model.jnt_range[i]
        if orig_lo == 0.0 and orig_hi == 0.0:
            continue  # unranged joints (e.g. the payload freejoint) have nothing to tighten
        assert lo == pytest.approx(orig_lo * 0.6)
        assert hi == pytest.approx(orig_hi * 0.6)


def test_dof_removed_deletes_the_joint_and_its_actuator():
    mutant_xml = dof_removed(ORIGINAL_XML, joint_name="j_shoulder")
    model = mujoco.MjModel.from_xml_string(mutant_xml)
    original_model = mujoco.MjModel.from_xml_string(ORIGINAL_XML)
    assert model.njnt == original_model.njnt - 1
    assert model.nu == original_model.nu - 1
    assert mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_JOINT, "j_shoulder") == -1


def test_dof_removed_unknown_joint_raises():
    with pytest.raises(PermutationError):
        dof_removed(ORIGINAL_XML, joint_name="j_does_not_exist")


def test_topology_swapped_changes_the_parent_body():
    mutant_xml = topology_swapped(ORIGINAL_XML, subtree="finger_left", new_parent="forearm")
    model = mujoco.MjModel.from_xml_string(mutant_xml)
    child_id = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_BODY, "finger_left")
    new_parent_id = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_BODY, "forearm")
    assert model.body_parentid[child_id] == new_parent_id


def test_topology_swapped_rejects_cycle():
    with pytest.raises(PermutationError):
        topology_swapped(ORIGINAL_XML, subtree="forearm", new_parent="finger_left")


def test_build_permutation_dispatches_by_name():
    mutant_xml = build_permutation(ORIGINAL_XML, "dof_removed", joint_name="j_wrist")
    model = mujoco.MjModel.from_xml_string(mutant_xml)
    assert mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_JOINT, "j_wrist") == -1


def test_build_permutation_rejects_unknown_class():
    with pytest.raises(PermutationError):
        build_permutation(ORIGINAL_XML, "not_a_real_class")


# --- tau -------------------------------------------------------------------------------------


def test_derive_tau_is_the_midpoint():
    assert derive_tau(d_control_max=0.0, d_handwritten_min=0.2) == pytest.approx(0.1)
    assert derive_tau(d_control_max=0.1, d_handwritten_min=0.3) == pytest.approx(0.2)


def test_derive_tau_raises_when_undefined():
    with pytest.raises(TauUndefinedError):
        derive_tau(d_control_max=0.3, d_handwritten_min=0.3)
    with pytest.raises(TauUndefinedError):
        derive_tau(d_control_max=0.5, d_handwritten_min=0.2)


# --- structural gates ------------------------------------------------------------------------


def test_run_g2_fails_when_diff_is_at_or_below_tau():
    a = _scaffold(scaffold_id="sc_a")
    b = dataclasses.replace(a, scaffold_id="sc_b")  # identical structure -> D = 0
    gate = run_g2(a, b, permutation_class="link_scaled", tau=0.1)
    assert not gate.passed
    assert gate.score == 0.0


def test_run_g2_passes_when_diff_exceeds_tau():
    a = build_dev_a_baseline()
    b = build_dev_b_baseline()
    tau = structural_diff(a, b) - 0.001  # just under the measured diff
    gate = run_g2(a, b, permutation_class="topology_swapped", tau=tau)
    assert gate.passed


def test_run_g2_dof_removed_hard_check_fails_scaffold_that_still_cites_deleted_joint():
    original = _scaffold(
        scaffold_id="sc_orig",
        reward_terms=(RewardTerm("a", 1.0, "1", ("joint.j_shoulder.qpos",), ""),),
    )
    # Structurally very different (D will be well above any reasonable tau) but still cites the
    # joint that dof_removed deleted -- the hard check must fail it regardless.
    mutant = _scaffold(
        scaffold_id="sc_mutant",
        reward_terms=(
            RewardTerm("a", 1.0, "1", ("joint.j_shoulder.qpos",), ""),
            RewardTerm("b", 1.0, "1", ("body.other",), ""),
        ),
    )
    gate = run_g2(
        original, mutant, permutation_class="dof_removed", tau=0.01, deleted_joint="j_shoulder"
    )
    assert not gate.passed
    assert gate.detail["dof_removed_hard_check"]["passed"] is False
    assert "joint.j_shoulder.qpos" in gate.detail["dof_removed_hard_check"]["offending_symbols"]


def test_run_g3_fails_for_identical_scaffolds():
    a = _scaffold()
    gate = run_g3(a, a, tau=0.05)
    assert not gate.passed
    assert gate.score == 0.0


def test_run_g3_passes_for_the_two_hand_written_baselines_at_their_own_calibrated_tau():
    a, b = build_dev_a_baseline(), build_dev_b_baseline()
    d = structural_diff(a, b)
    tau = d / 2  # anything strictly below the measured diff
    gate = run_g3(a, b, tau=tau)
    assert gate.passed


# --- the actual required outcome: the negative control fails everything -----------------------


def test_negative_control_is_schema_blind_across_all_four_permutation_classes():
    """Corroborates step4_run.py's object-identity proof, but per permutation class and via a
    real generated mutant file rather than an assumption: the control run against dev-a and
    against a real mutant of dev-a return literally the same object, so D = 0 for all of them."""

    import tempfile
    from pathlib import Path as _Path

    from packages.research.loop_research.permutations import PERMUTATION_CLASSES

    original = run_static_scaffold_loop(DEV_A_SCHEMA, "lift the payload to shelf height")
    with tempfile.TemporaryDirectory() as tmp:
        for permutation_class in PERMUTATION_CLASSES:
            kwargs = {"joint_name": "j_shoulder"} if permutation_class == "dof_removed" else {}
            mutant_xml = build_permutation(ORIGINAL_XML, permutation_class, **kwargs)
            mutant_path = _Path(tmp) / f"{permutation_class}.xml"
            mutant_path.write_text(mutant_xml)
            mutant_scaffold = run_static_scaffold_loop(mutant_path, "lift the payload to shelf height")
            assert mutant_scaffold is original
            assert structural_diff(original, mutant_scaffold) == 0.0
