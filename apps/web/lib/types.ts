export interface Er16Plan {
  task_goal: string;
  affordances: string[];
  success_criteria: string;
  search_queries: string[];
}

export interface IngestJob {
  job_id: string;
  status: string;
  er16_plan: Er16Plan;
  video_id: string | null;
  gvhmr_job_id?: string | null;
  reference_source_type?: "youtube" | "droid" | "none" | null;
  reference_payload?: Record<string, unknown> | null;
  selected_query?: string;
  selection_rationale?: string;
  candidate_reviews?: Array<Record<string, unknown>>;
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

export interface CandidateTelemetry {
  candidate_id: "A" | "B" | "C";
  estimated_total_cost_usd: number | null;
  estimated_mass_kg: number;
  payload_capacity_kg: number;
  payload_margin_kg: number;
  estimated_reach_m: number;
  actuator_torque_nm: number;
  estimated_backlash_deg: number;
  estimated_bandwidth_hz: number;
  procurement_confidence: number;
  design_quality_score: number;
  risk_flags: string[];
  summary: string;
}

export interface EngineeringSceneNode {
  name: string;
  component_id: string;
  structure_id: string;
  display_name: string;
  component_kind: string;
  role_label: string;
  material_key: string;
  material_label: string;
  position: [number, number, number];
  scale: [number, number, number];
  bounds_m: [number, number, number];
  focus_summary: string;
  highlight_color?: [number, number, number, number];
  color?: [number, number, number, number];
}

export interface EngineeringSceneJoint {
  name: string;
  joint_kind: string;
  position: [number, number, number];
}

export interface EngineeringScene {
  render_mode: string;
  nodes: EngineeringSceneNode[];
  joints: EngineeringSceneJoint[];
  stats: Record<string, unknown>;
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
  candidate_telemetry: Record<"A" | "B" | "C", CandidateTelemetry>;
  render_payloads: Record<
    "A" | "B" | "C",
    {
      candidate_id: "A" | "B" | "C";
      topology_label: string;
      view_modes: Array<"concept" | "engineering" | "joints" | "components">;
      engineering_ready: boolean;
      render_glb: string;
      ui_scene: EngineeringScene;
      mjcf: string;
      joint_count: number;
    }
  >;
}

export interface DesignSpecResponse {
  design_id: string;
  candidate_id: "A" | "B" | "C";
  revision_id: string;
  revision_number: number;
  design: RobotDesignCandidate;
  telemetry: CandidateTelemetry;
  bom: BOMOutput | null;
  render: {
    candidate_id: "A" | "B" | "C";
    topology_label: string;
    view_modes: Array<"concept" | "engineering" | "joints" | "components">;
    engineering_ready: boolean;
    render_glb: string;
    ui_scene: EngineeringScene;
    mjcf: string;
    joint_count: number;
  } | null;
  approval_events: Array<Record<string, unknown>>;
}

export interface DesignCheckpoint {
  id: string;
  db_id: string;
  checkpoint_key: string;
  label: string;
  title: string;
  summary: string;
  rows_json: Array<{ field: string; before: string; after: string }>;
  status: string;
  decision: "pending" | "approved" | "denied" | "parked";
  note?: string | null;
  metadata_json?: Record<string, unknown> | null;
}

export interface DesignTaskRun {
  id: string;
  design_id: string;
  revision_id?: string | null;
  task_key: string;
  status: "waiting" | "running" | "review" | "active" | "done";
  summary: string;
  payload_json?: Record<string, unknown> | null;
  result_json?: Record<string, unknown> | null;
  created_at: string;
}

export interface DesignExportsResponse {
  design_id: string;
  items: Array<{
    label: string;
    subtitle: string;
    status: string;
  }>;
  artifacts: Record<string, unknown>;
}

export interface ValidationCheckResult {
  name: string;
  status: "pass" | "warning" | "fail";
  summary: string;
  details: string[];
  category: "structural" | "task" | "compiler" | "render" | "simulation" | "procurement";
}

export interface DesignValidationReport {
  design_id: string;
  revision_id: string;
  candidate_id: "A" | "B" | "C";
  is_valid: boolean;
  summary: string;
  failure_categories: Array<"structural" | "task" | "compiler" | "render" | "simulation" | "procurement">;
  checks: ValidationCheckResult[];
  render_checks: Record<string, string | number | boolean>;
  artifact_paths: Record<string, string>;
  output_path?: string | null;
}

export interface RecordClipResponse {
  task_run: DesignTaskRun;
  playback: {
    candidate_id: "A" | "B" | "C";
    task_goal: string;
    motion_profile: string;
    duration_s: number;
    camera_mode: string;
    estimated_reach_m: number;
    source_type:
      | "youtube_gvhmr"
      | "youtube_reference"
      | "droid_episode"
      | "droid_window"
      | "simulated_policy"
      | "unavailable";
    source_ready: boolean;
    source_ref: Record<string, unknown>;
    provenance_summary: string;
  };
}

export interface HitlRecipientSetup {
  id: string;
  channel: string;
  recipient: string;
  display_name?: string | null;
  thread_key?: string | null;
  consent_status: "pending" | "confirmed" | "revoked" | string;
  is_default: boolean;
}

export interface HitlSetupResponse {
  provider_ready: boolean;
  recipient: HitlRecipientSetup | null;
  can_send: boolean;
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
