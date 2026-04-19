import type { FallbackRanking, RobotDesignCandidate } from "@/lib/types";

export const videoPrompt =
  "carry a storage bin up one flight of stairs";

export const designReviewPlan = {
  task_goal: "carry a storage bin up one flight of stairs",
  affordances: [
    "stairs",
    "payload stability",
    "dual-arm grasping",
    "indoor mobility",
  ],
  success_criteria:
    "Climb one full flight while keeping a 4 kg storage bin stable and centered.",
};

export const designReviewVideos = [
  {
    id: "stairs_box_01",
    title: "person carrying storage bin upstairs side view",
    thumbnail: "https://img.youtube.com/vi/dQw4w9WgXcQ/mqdefault.jpg",
    duration: "1:28",
  },
  {
    id: "stairs_box_02",
    title: "box carry staircase full body reference",
    thumbnail: "https://img.youtube.com/vi/oHg5SJYRHA0/mqdefault.jpg",
    duration: "0:54",
  },
  {
    id: "stairs_box_03",
    title: "upstairs bin carry fixed camera",
    thumbnail: "https://img.youtube.com/vi/FTQbiNvZqaY/mqdefault.jpg",
    duration: "1:12",
  },
  {
    id: "stairs_box_04",
    title: "payload carry on stairs profile",
    thumbnail: "https://img.youtube.com/vi/9bZkp7q19f0/mqdefault.jpg",
    duration: "0:46",
  },
];

export const designIds: Record<"A" | "B" | "C", string> = {
  A: "design-a",
  B: "design-b",
  C: "design-c",
};

export const designReviewCandidates: RobotDesignCandidate[] = [
  {
    candidate_id: "A",
    embodiment_class: "hybrid",
    num_legs: 2,
    num_arms: 2,
    has_torso: true,
    torso_length_m: 0.46,
    leg_length_m: 0.62,
    arm_length_m: 0.58,
    leg_dof: 4,
    arm_dof: 5,
    spine_dof: 2,
    actuator_class: "bldc",
    actuator_torque_nm: 28,
    total_mass_kg: 17,
    payload_capacity_kg: 4,
    sensor_package: ["imu", "camera", "force", "encoder"],
    rationale:
      "Lean climbing hybrid with dual grasping limbs, explicit surface attachment strategy, and centered payload support.",
    confidence: 0.86,
  },
  {
    candidate_id: "B",
    embodiment_class: "biped",
    num_legs: 2,
    num_arms: 2,
    has_torso: true,
    torso_length_m: 0.5,
    leg_length_m: 0.66,
    arm_length_m: 0.52,
    leg_dof: 4,
    arm_dof: 4,
    spine_dof: 2,
    actuator_class: "bldc",
    actuator_torque_nm: 24,
    total_mass_kg: 18.5,
    payload_capacity_kg: 3.4,
    sensor_package: ["imu", "camera", "encoder", "force"],
    rationale:
      "Humanoid-style wall climber with dual-arm grasping and vertical support strategy for rough surfaces.",
    confidence: 0.8,
  },
  {
    candidate_id: "C",
    embodiment_class: "quadruped",
    num_legs: 4,
    num_arms: 0,
    has_torso: true,
    torso_length_m: 0.54,
    leg_length_m: 0.42,
    arm_length_m: 0,
    leg_dof: 4,
    arm_dof: 0,
    spine_dof: 1,
    actuator_class: "bldc",
    actuator_torque_nm: 22,
    total_mass_kg: 20,
    payload_capacity_kg: 3.6,
    sensor_package: ["imu", "camera", "encoder"],
    rationale:
      "Conservative rough-terrain climber using hooked feet for surface attachment and distributed load support.",
    confidence: 0.74,
  },
];

export const designReviewRankings: FallbackRanking[] = [
  {
    candidate_id: "C",
    kinematic_feasibility: 1,
    static_stability: 1,
    bom_confidence: 1,
    retargetability: 0.95,
    total_score: 0.99,
  },
  {
    candidate_id: "A",
    kinematic_feasibility: 1,
    static_stability: 0.5,
    bom_confidence: 1,
    retargetability: 1,
    total_score: 0.875,
  },
  {
    candidate_id: "B",
    kinematic_feasibility: 1,
    static_stability: 0.5,
    bom_confidence: 0.92,
    retargetability: 0.85,
    total_score: 0.829,
  },
];

export const programDraft = `# Research Agenda

## Objective
- Develop a stair-capable morphology that keeps a 4 kg storage bin stable through ascent.

## Iteration Priorities
1. Validate dual-arm grasp geometry against stair clearance.
2. Compare center-of-mass drift for hybrid vs biped concepts.
3. Export the best candidate for controller and BOM review.

## Approval Gate
- Ship only if payload stability and climb repeatability both clear review thresholds.`;
