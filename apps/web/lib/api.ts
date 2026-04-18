import type { IngestJob, EvolutionCreated, Evolution, GenerateDesignsResponse, BOMOutput } from "./types";

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
  ingest: {
    start: (prompt: string): Promise<IngestJob> =>
      req("/ingest", { method: "POST", body: JSON.stringify({ prompt }) }),
    get: (jobId: string) => req<{ status: string; er16_plan_json: string }>(`/ingest/${jobId}`),
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
    getBom: (designId: string): Promise<BOMOutput> => req(`/designs/${designId}/bom`),
    select: (designId: string, evolutionId: string) =>
      req(`/designs/${designId}/select`, {
        method: "POST",
        body: JSON.stringify({ evolution_id: evolutionId }),
      }),
    byIngest: (ingestJobId: string) => req<Record<string, unknown>[]>(`/designs/by-ingest/${ingestJobId}`),
  },
};
