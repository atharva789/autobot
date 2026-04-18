from packages.pipeline.types import MorphologyParams, TrialResult, EvolutionConfig
import dataclasses, pytest

def test_morphology_params_is_frozen():
    p = MorphologyParams(num_arms=2, num_legs=2, has_torso=True,
                         torso_length=0.4, arm_length=0.5, leg_length=0.7,
                         arm_dof=5, leg_dof=4, spine_dof=1,
                         joint_damping=0.1, joint_stiffness=10.0, friction=0.8)
    with pytest.raises((dataclasses.FrozenInstanceError, AttributeError)):
        p.num_arms = 99  # direct assignment triggers frozen guard in all Python versions

def test_trial_result_fields():
    r = TrialResult(tracking_error=0.1, er16_success_prob=0.8,
                    fitness_score=0.78, replay_mp4_url="https://x",
                    controller_ckpt_url="https://y", trajectory_npz_url="https://z",
                    reasoning_md="tried longer arms")
    assert r.fitness_score == 0.78

def test_evolution_config_defaults():
    c = EvolutionConfig()
    assert c.max_iters == 20
    assert c.cost_alarm_usd == 50.0
    assert c.fitness_weights == (0.6, 0.4)
