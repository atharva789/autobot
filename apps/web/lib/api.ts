import type {
  IngestJob,
  EvolutionCreated,
  Evolution,
  GenerateDesignsResponse,
  BOMOutput,
  DesignSpecResponse,
  DesignCheckpoint,
  DesignTaskRun,
  DesignExportsResponse,
  DesignValidationReport,
  RecordClipResponse,
  HitlSetupResponse,
} from "./types";

const BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

async function req<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...init,
  });
  if (!res.ok) {
    let detail = `API ${path} -> ${res.status}`;
    try {
      const body = await res.json();
      if (typeof body?.detail === "string") {
        detail = body.detail;
      } else if (body?.detail?.error) {
        detail = body.detail.error;
        if (body.detail.migration) {
          detail += ` Apply ${body.detail.migration}.`;
        }
      }
    } catch {
      // ignore JSON parse failure and keep generic detail
    }
    throw new Error(detail);
  }
  return res.json() as Promise<T>;
}

export const api = {
  get: <T>(path: string): Promise<T> => req(path),
  post: <T>(path: string, body?: unknown): Promise<T> =>
    req(path, {
      method: "POST",
      body: body === undefined ? undefined : JSON.stringify(body),
    }),
  ingest: {
    start: (prompt: string): Promise<IngestJob> =>
      req("/ingest", { method: "POST", body: JSON.stringify({ prompt }) }),
    get: (jobId: string): Promise<{ er16_plan_json: string; [key: string]: unknown }> =>
      req(`/ingest/${jobId}`),
  },
  evolutions: {
    create: (runId: string, ingestJobId: string): Promise<EvolutionCreated> =>
      req("/evolutions", {
        method: "POST",
        body: JSON.stringify({ run_id: runId, ingest_job_id: ingestJobId }),
      }),
    approveProgram: (evoId: string, content: string) =>
      req(`/evolutions/${evoId}/approve-program`, {
        method: "POST",
        body: JSON.stringify({ content }),
      }),
    stop: (evoId: string) => req(`/evolutions/${evoId}/stop`, { method: "POST" }),
    markBest: (evoId: string, iterId: string) =>
      req(`/evolutions/${evoId}/mark-best/${iterId}`, { method: "POST" }),
    get: (evoId: string): Promise<Evolution> => req(`/evolutions/${evoId}`),
  },
  designs: {
    generate: (ingestJobId: string): Promise<GenerateDesignsResponse> =>
      req("/designs/generate", {
        method: "POST",
        body: JSON.stringify({ ingest_job_id: ingestJobId }),
      }),
    get: (designId: string) => req<Record<string, unknown>>(`/designs/${designId}`),
    getSpec: (designId: string): Promise<DesignSpecResponse> => req(`/designs/${designId}/spec`),
    getCheckpoints: (designId: string): Promise<{ design_id: string; revision_id: string; items: DesignCheckpoint[] }> =>
      req(`/designs/${designId}/checkpoints`),
    decideCheckpoint: (
      designId: string,
      checkpointId: string,
      decision: "approved" | "denied" | "parked",
      note?: string,
    ) =>
      req(`/designs/${designId}/checkpoints/${checkpointId}/decision`, {
        method: "POST",
        body: JSON.stringify({ decision, note }),
      }),
    getTasks: (designId: string): Promise<{ design_id: string; items: DesignTaskRun[] }> =>
      req(`/designs/${designId}/tasks`),
    runTask: (designId: string, taskKey: string, payload?: Record<string, unknown>) =>
      req<{ task_run: DesignTaskRun }>(`/designs/${designId}/tasks`, {
        method: "POST",
        body: JSON.stringify({ task_key: taskKey, payload }),
      }),
    getExports: (designId: string): Promise<DesignExportsResponse> => req(`/designs/${designId}/exports`),
    getValidation: (designId: string): Promise<{ design_id: string; report: DesignValidationReport; artifacts: Record<string, unknown>[] }> =>
      req(`/designs/${designId}/validation`),
    recordClip: (designId: string, mode = "task_preview"): Promise<RecordClipResponse> =>
      req(`/designs/${designId}/record-clip`, {
        method: "POST",
        body: JSON.stringify({ mode }),
      }),
    revise: (designId: string, instruction: string) =>
      req<{ design_id: string; revision_id: string; revision_number: number; spec: DesignSpecResponse }>(`/designs/${designId}/revise`, {
        method: "POST",
        body: JSON.stringify({ instruction }),
      }),
    getBom: (designId: string): Promise<BOMOutput> => req(`/designs/${designId}/bom`),
    select: (designId: string, evolutionId: string) =>
      req(`/designs/${designId}/select`, {
        method: "POST",
        body: JSON.stringify({ evolution_id: evolutionId }),
      }),
    byIngest: (ingestJobId: string) => req<Record<string, unknown>[]>(`/designs/by-ingest/${ingestJobId}`),
  },
  hitl: {
    getSetup: (): Promise<HitlSetupResponse> => req("/hitl/setup"),
    saveSetup: (payload: { recipient: string; display_name?: string; thread_key?: string }): Promise<HitlSetupResponse> =>
      req("/hitl/setup", {
        method: "POST",
        body: JSON.stringify(payload),
      }),
    confirmSetup: (recipientId: string): Promise<HitlSetupResponse> =>
      req("/hitl/setup/confirm", {
        method: "POST",
        body: JSON.stringify({ recipient_id: recipientId }),
      }),
    sendTest: (payload?: { recipient?: string; thread_key?: string }) =>
      req("/hitl/setup/test", {
        method: "POST",
        body: JSON.stringify(payload ?? {}),
      }),
  },
};
