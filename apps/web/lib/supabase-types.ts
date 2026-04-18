// Auto-generated stub — replace with: supabase gen types typescript --linked > apps/web/lib/supabase-types.ts
export type Json = string | number | boolean | null | { [key: string]: Json } | Json[];

export interface Database {
  public: {
    Tables: {
      evolutions: {
        Row: {
          id: string;
          run_id: string | null;
          program_md: string | null;
          status: string;
          best_iteration_id: string | null;
          total_cost_usd: number | null;
          started_at: string | null;
          completed_at: string | null;
        };
        Insert: Partial<Database["public"]["Tables"]["evolutions"]["Row"]> & { id: string; status: string };
        Update: Partial<Database["public"]["Tables"]["evolutions"]["Row"]>;
      };
      morphologies: {
        Row: {
          id: string;
          urdf_url: string | null;
          latent_z_json: string | null;
          params_json: string | null;
          num_dof: number | null;
          created_at: string | null;
        };
        Insert: Partial<Database["public"]["Tables"]["morphologies"]["Row"]> & { id: string };
        Update: Partial<Database["public"]["Tables"]["morphologies"]["Row"]>;
      };
      iterations: {
        Row: {
          id: string;
          evolution_id: string | null;
          iter_num: number;
          morphology_id: string | null;
          controller_ckpt_url: string | null;
          trajectory_npz_url: string | null;
          replay_mp4_url: string | null;
          fitness_score: number | null;
          tracking_error: number | null;
          er16_success_prob: number | null;
          reasoning_log: string | null;
          train_py_diff: string | null;
          morph_factory_diff: string | null;
          created_at: string | null;
        };
        Insert: Partial<Database["public"]["Tables"]["iterations"]["Row"]> & { id: string; iter_num: number };
        Update: Partial<Database["public"]["Tables"]["iterations"]["Row"]>;
      };
      ingest_jobs: {
        Row: {
          id: string;
          source_url: string | null;
          er16_plan_json: string | null;
          gvhmr_job_id: string | null;
          smpl_path: string | null;
          status: string;
          created_at: string | null;
        };
        Insert: Partial<Database["public"]["Tables"]["ingest_jobs"]["Row"]> & { id: string; status: string };
        Update: Partial<Database["public"]["Tables"]["ingest_jobs"]["Row"]>;
      };
      program_md_drafts: {
        Row: {
          id: string;
          evolution_id: string | null;
          generator: string | null;
          draft_content: string | null;
          approved: boolean | null;
          approved_at: string | null;
          user_edited_content: string | null;
        };
        Insert: Partial<Database["public"]["Tables"]["program_md_drafts"]["Row"]> & { id: string };
        Update: Partial<Database["public"]["Tables"]["program_md_drafts"]["Row"]>;
      };
    };
    Views: Record<string, never>;
    Functions: Record<string, never>;
    Enums: Record<string, never>;
  };
}
