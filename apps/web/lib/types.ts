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
