export interface Er16Plan {
  task_goal: string;
  affordances: string[];
  success_criteria: string;
  search_queries: string[];
}

export interface IngestJob {
  job_id: string;
  er16_plan: Er16Plan;
  video_id: string;
}

export interface EvolutionCreated {
  evolution_id: string;
  draft_id: string;
  draft_content: string;
}

export interface Iteration {
  id: string;
  evolution_id: string;
  iter_num: number;
  fitness_score: number | null;
  tracking_error: number | null;
  er16_success_prob: number | null;
  replay_mp4_url: string | null;
  controller_ckpt_url: string | null;
  reasoning_log: string | null;
  train_py_diff: string | null;
  morph_factory_diff: string | null;
  created_at: string;
}

export interface Evolution {
  id: string;
  run_id: string;
  status: "pending" | "running" | "stopped" | "done";
  best_iteration_id: string | null;
  total_cost_usd: number;
  program_md: string | null;
}

export interface RobotDesignCandidate {
  candidate_id: "A" | "B" | "C";
  embodiment_class: string;
  num_legs: number;
  num_arms: number;
  has_torso: boolean;
  torso_length_m: number;
  leg_length_m: number;
  arm_length_m: number;
  leg_dof: number;
  arm_dof: number;
  spine_dof: number;
  actuator_class: string;
  actuator_torque_nm: number;
  total_mass_kg: number;
  payload_capacity_kg: number;
  sensor_package: string[];
  rationale: string;
  confidence: number;
}

export interface FallbackRanking {
  candidate_id: "A" | "B" | "C";
  kinematic_feasibility: number;
  static_stability: number;
  bom_confidence: number;
  retargetability: number;
  total_score: number;
}

export interface GenerateDesignsResponse {
  design_ids: Record<"A" | "B" | "C", string>;
  candidates: RobotDesignCandidate[];
  model_preferred_id: "A" | "B" | "C";
  fallback_rankings: FallbackRanking[];
  selection_rationale: string;
}

export interface BOMItem {
  part_name: string;
  sku: string | null;
  quantity: number;
  unit_price_usd: number | null;
  vendor: string | null;
  availability: "in_stock" | "limited" | "backorder" | "unknown";
  requires_review: boolean;
}

export interface BOMOutput {
  candidate_id: "A" | "B" | "C";
  structural_items: BOMItem[];
  actuator_items: BOMItem[];
  electronics_items: BOMItem[];
  fastener_items: BOMItem[];
  total_cost_usd: number | null;
  procurement_confidence: number;
  missing_items: string[];
}
