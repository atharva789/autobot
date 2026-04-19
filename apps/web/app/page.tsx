"use client";

import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { AnimatePresence, LayoutGroup, motion } from "motion/react";
import {
  ArrowRight,
  Bot,
  Cable,
  CheckCircle2,
  ChevronRight,
  Circle,
  CircleDashed,
  ClipboardCheck,
  Component,
  Download,
  LoaderCircle,
  Orbit,
  Package2,
  PencilLine,
  SendHorizontal,
  ShieldCheck,
  Sparkles,
  TriangleAlert,
} from "lucide-react";

import { MorphologyViewer } from "@/components/MorphologyViewer";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { api } from "@/lib/api";
import type {
  BOMItem,
  BOMOutput,
  CandidateTelemetry,
  DesignCheckpoint,
  DesignExportsResponse,
  DesignSpecResponse,
  DesignTaskRun,
  EngineeringSceneNode,
  Er16Plan,
  GenerateDesignsResponse,
  HitlSetupResponse,
  RobotDesignCandidate,
} from "@/lib/types";

type WorkspaceStage = "prompt" | "workspace";
type DetailViewMode = "concept" | "engineering" | "joints" | "components";
type CandidateId = "A" | "B" | "C";
type TaskStatus = "review" | "active" | "waiting" | "done";
type CheckpointDecision = "pending" | "approved" | "denied" | "parked";
type InspectorTab = "spec" | "export" | "components";

type WorkspaceTask = {
  id: string;
  title: string;
  subtitle: string;
  status: TaskStatus;
  age: string;
};

const EXAMPLE_PROMPTS = [
  "carry a storage bin up one flight of stairs",
  "descend a slippery slope while moving a rescue payload",
  "climb a rock wall while carrying a rope pack on its back",
];

const QUICK_ACTIONS = [
  "compare candidate B",
  "send review poll",
  "export URDF",
  "cost BOM vs budget",
];

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

const VIEW_MODES: Array<{ id: DetailViewMode; label: string }> = [
  { id: "concept", label: "Concept" },
  { id: "engineering", label: "Engineering" },
  { id: "joints", label: "Joints" },
  { id: "components", label: "Components" },
];

function sleep(ms: number) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function clamp01(value: number) {
  return Math.max(0, Math.min(1, value));
}

function shortTaskTitle(prompt: string) {
  const cleaned = prompt.replace(/^make (a|the)\s+/i, "").replace(/^design\s+/i, "").trim();
  if (!cleaned) return "robot task";
  if (cleaned.length <= 36) return cleaned;
  return `${cleaned.slice(0, 33).trimEnd()}...`;
}

function topologyLabel(candidate: RobotDesignCandidate) {
  return `${candidate.embodiment_class} · ${candidate.num_legs}L · ${candidate.num_arms}A · ${candidate.spine_dof}S`;
}

function countDof(candidate: RobotDesignCandidate) {
  return candidate.num_legs * candidate.leg_dof + candidate.num_arms * candidate.arm_dof + candidate.spine_dof;
}

function actuatorDisplayName(candidate: RobotDesignCandidate, bom?: BOMOutput | null) {
  const primaryActuator = bom?.actuator_items?.[0];
  if (primaryActuator?.sku) return `${candidate.actuator_class} · ${primaryActuator.sku}`;
  return `${candidate.actuator_class} · T${Math.round(candidate.actuator_torque_nm)}`;
}

function baselineActuatorName(candidate: RobotDesignCandidate) {
  const map: Record<string, string> = {
    bldc: "servo · S-18",
    servo: "stepper · N24",
    stepper: "servo · S-18",
    hydraulic: "bldc · BX-45",
  };
  return map[candidate.actuator_class] ?? "servo · S-18";
}

function formatMoney(value: number | null | undefined) {
  if (typeof value !== "number" || Number.isNaN(value)) return "n/a";
  return `$${Math.round(value).toLocaleString()}`;
}

function telemetryCostChip(telemetry?: CandidateTelemetry | null) {
  return telemetry ? formatMoney(telemetry.estimated_total_cost_usd) : "n/a";
}

function formatAgeLabel(createdAt?: string | null) {
  if (!createdAt) return "now";
  const parsed = Date.parse(createdAt);
  if (Number.isNaN(parsed)) return "now";
  const deltaMs = Date.now() - parsed;
  const deltaMin = Math.max(0, Math.round(deltaMs / 60000));
  if (deltaMin < 1) return "now";
  return `${deltaMin}m`;
}

function mapTaskRunsToWorkspaceTasks(taskRuns: DesignTaskRun[]): WorkspaceTask[] {
  return taskRuns.map((task) => ({
    id: task.id,
    title: task.task_key.replaceAll("_", " "),
    subtitle: task.summary,
    status:
      task.status === "running"
        ? "active"
        : task.status === "done"
          ? "done"
          : task.status === "review"
            ? "review"
            : "waiting",
    age: formatAgeLabel(task.created_at),
  }));
}

function buildActuatorRows(candidate: RobotDesignCandidate, bom: BOMOutput | null) {
  const primaryActuator = bom?.actuator_items?.[0];
  const jointCount = Math.min(6, Math.max(3, countDof(candidate)));
  return Array.from({ length: jointCount }, (_, index) => {
    const torqueScale = 1 - index * 0.12;
    const ratio = Math.max(30, Math.round((candidate.actuator_torque_nm * 8) / Math.max(0.6, torqueScale)));
    const torque = Math.max(0.8, candidate.actuator_torque_nm * torqueScale);
    return {
      joint: `J${index + 1}`,
      type: index === 1 && candidate.num_arms > 0 ? candidate.actuator_class : index >= 4 ? "stepper" : candidate.actuator_class,
      torque: `${torque.toFixed(torque >= 10 ? 0 : 1)} Nm`,
      ratio: `${ratio}:1`,
      sku: index === 1 ? primaryActuator?.sku : undefined,
    };
  });
}

function buildTaskAlignment(candidate: RobotDesignCandidate, telemetry: CandidateTelemetry | null, plan: Er16Plan | null) {
  const targetPayload = plan?.success_criteria?.match(/(\d+(\.\d+)?)\s*kg/i);
  const payloadTarget = targetPayload ? Number(targetPayload[1]) : Math.max(1.5, candidate.payload_capacity_kg * 0.66);
  const reachTarget = candidate.num_arms > 0 ? 0.5 : 0.35;
  const bandwidthTarget = 50;

  return [
    {
      label: `reach ≥ ${reachTarget.toFixed(1)} m`,
      value: `${telemetry?.estimated_reach_m.toFixed(2) ?? candidate.arm_length_m.toFixed(2)} m`,
      progress: clamp01((telemetry?.estimated_reach_m ?? candidate.arm_length_m) / reachTarget),
    },
    {
      label: `payload ≤ ${payloadTarget.toFixed(1)} kg`,
      value: `${candidate.payload_capacity_kg.toFixed(2)} kg`,
      progress: clamp01(candidate.payload_capacity_kg / payloadTarget),
    },
    {
      label: `bandwidth ≥ ${bandwidthTarget} Hz`,
      value: `${telemetry?.estimated_bandwidth_hz.toFixed(0) ?? "0"} Hz`,
      progress: clamp01((telemetry?.estimated_bandwidth_hz ?? 0) / bandwidthTarget),
    },
    {
      label: "procurement confidence",
      value: `${Math.round((telemetry?.procurement_confidence ?? 0) * 100)}%`,
      progress: telemetry?.procurement_confidence ?? 0,
    },
  ];
}

function buildExportTargets() {
  return [
    { label: "URDF", subtitle: "ROS 2 Humble", status: "ready" },
    { label: "MJCF", subtitle: "MuJoCo 3.2", status: "ready" },
    { label: "USD", subtitle: "Isaac Sim 4.5", status: "ready" },
    { label: "STEP", subtitle: "CAD", status: "queued" },
  ];
}

function componentKindLabel(kind: string) {
  return kind.replaceAll("_", " ");
}

function taskStatusTone(status: TaskStatus) {
  switch (status) {
    case "review":
      return "warning";
    case "done":
      return "success";
    default:
      return "muted";
  }
}

function maskRecipient(recipient?: string | null) {
  if (!recipient) return "not configured";
  if (recipient.length <= 4) return recipient;
  return `${"*".repeat(Math.max(0, recipient.length - 4))}${recipient.slice(-4)}`;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

function isDesignTaskRun(value: unknown): value is DesignTaskRun {
  if (!isRecord(value)) return false;
  return (
    typeof value.id === "string" &&
    typeof value.design_id === "string" &&
    typeof value.task_key === "string" &&
    typeof value.status === "string" &&
    typeof value.summary === "string" &&
    typeof value.created_at === "string"
  );
}

function isPlaybackPayload(
  value: unknown,
): value is { playback: NonNullable<Awaited<ReturnType<typeof api.designs.recordClip>>["playback"]> } {
  return isRecord(value) && typeof value.playback === "object" && value.playback !== null;
}

function PhotonSetupPanel({
  hitlSetup,
  recipient,
  displayName,
  threadKey,
  consentChecked,
  onRecipientChange,
  onDisplayNameChange,
  onThreadKeyChange,
  onConsentChange,
  onSave,
  onSendTest,
  saving,
  sendingTest,
}: {
  hitlSetup: HitlSetupResponse | null;
  recipient: string;
  displayName: string;
  threadKey: string;
  consentChecked: boolean;
  onRecipientChange: (value: string) => void;
  onDisplayNameChange: (value: string) => void;
  onThreadKeyChange: (value: string) => void;
  onConsentChange: (value: boolean) => void;
  onSave: () => void;
  onSendTest: () => void;
  saving: boolean;
  sendingTest: boolean;
}) {
  return (
    <div className="mt-4 rounded-[12px] border border-white/8 bg-black/28 px-3 py-3">
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="autobot-label">Photon setup</p>
          <p className="mt-1 text-sm text-slate-400">
            Provide a phone number for HITL review polls and confirm consent before sending.
          </p>
        </div>
        <span className="autobot-status" data-tone={hitlSetup?.can_send ? "success" : "warning"}>
          {hitlSetup?.can_send ? "ready" : hitlSetup?.recipient ? hitlSetup.recipient.consent_status : "setup required"}
        </span>
      </div>

      <div className="mt-3 grid gap-2">
        <input
          value={displayName}
          onChange={(event) => onDisplayNameChange(event.target.value)}
          placeholder="Name"
          className="rounded-md border border-white/8 bg-white/3 px-3 py-2 text-sm text-slate-100 outline-none"
        />
        <input
          value={recipient}
          onChange={(event) => onRecipientChange(event.target.value)}
          placeholder="Phone number"
          className="rounded-md border border-white/8 bg-white/3 px-3 py-2 text-sm text-slate-100 outline-none"
        />
        <input
          value={threadKey}
          onChange={(event) => onThreadKeyChange(event.target.value)}
          placeholder="Thread key (optional)"
          className="rounded-md border border-white/8 bg-white/3 px-3 py-2 text-sm text-slate-100 outline-none"
        />
      </div>

      <label className="mt-3 flex items-start gap-2 text-sm text-slate-300">
        <input
          type="checkbox"
          checked={consentChecked}
          onChange={(event) => onConsentChange(event.target.checked)}
          className="mt-1"
        />
        <span>I consent to receive robot review alerts and polls at this phone number.</span>
      </label>

      {hitlSetup?.recipient ? (
        <p className="mt-3 text-xs text-slate-500">
          Current recipient: {maskRecipient(hitlSetup.recipient.recipient)} · consent {hitlSetup.recipient.consent_status}
        </p>
      ) : null}

      <div className="mt-3 flex items-center gap-2">
        <Button
          onClick={onSave}
          disabled={saving || !recipient.trim()}
          className="h-9 bg-[#72cf63] text-[#08110b] hover:bg-[#87dc79]"
        >
          {saving ? "Saving…" : "Save & consent"}
        </Button>
        <Button
          variant="outline"
          onClick={onSendTest}
          disabled={sendingTest || !hitlSetup?.can_send}
          className="h-9 border-white/12 bg-white/3 text-slate-100 hover:bg-white/7"
        >
          {sendingTest ? "Sending…" : "Send test text"}
        </Button>
      </div>
    </div>
  );
}

function CheckpointCard({
  checkpoint,
  decision,
  onDecision,
}: {
  checkpoint: DesignCheckpoint;
  decision: CheckpointDecision;
  onDecision: (decision: Exclude<CheckpointDecision, "pending">) => void;
}) {
  const accent =
    decision === "approved"
      ? "rgba(74,222,128,0.22)"
      : decision === "denied"
        ? "rgba(248,113,113,0.18)"
        : "rgba(132,204,22,0.16)";

  return (
    <div
      className="autobot-panel max-w-[560px] px-5 py-4"
      style={{ boxShadow: `0 0 0 1px ${accent} inset` }}
    >
      <div className="flex items-start justify-between gap-3">
        <div>
          <div className="flex items-center gap-3">
            <span className="autobot-status" data-tone={checkpoint.label === "Budget" ? "warning" : "success"}>
              {checkpoint.label}
            </span>
            <h3 className="text-[15px] font-semibold text-slate-100">{checkpoint.title}</h3>
          </div>
          <p className="mt-3 max-w-[54ch] text-sm leading-6 text-slate-400">{checkpoint.summary}</p>
        </div>
        <button
          className="text-xs uppercase tracking-[0.22em] text-slate-500 transition hover:text-slate-300"
          onClick={() => onDecision("parked")}
        >
          Park ×
        </button>
      </div>
      <div className="mt-4 overflow-hidden rounded-[12px] border border-white/7">
        <table className="autobot-table text-sm">
          <thead>
            <tr>
              <th>Field</th>
              <th>Before</th>
              <th>After</th>
            </tr>
          </thead>
          <tbody>
            {(checkpoint.rows_json ?? []).map((row) => (
              <tr key={row.field}>
                <td className="text-slate-400">{row.field}</td>
                <td className="text-slate-500 line-through">{row.before}</td>
                <td className="font-medium text-slate-100">{row.after}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="mt-4 flex items-center gap-3">
        <Button
          className="bg-[#72cf63] text-[#08110b] hover:bg-[#87dc79]"
          onClick={() => onDecision("approved")}
        >
          Approve
        </Button>
        <Button
          variant="outline"
          className="border-white/12 bg-white/3 text-slate-100 hover:bg-white/7"
          onClick={() => onDecision("denied")}
        >
          Deny
        </Button>
        <Button
          variant="outline"
          className="border-white/12 bg-white/3 text-slate-400 hover:bg-white/7"
          onClick={() => onDecision("parked")}
        >
          Guide...
        </Button>
      </div>
    </div>
  );
}

function TaskRail({
  prompt,
  tasks,
  activeCount,
  waitingCount,
  selectedCandidateId,
  onSelectCandidate,
  selectedQuery,
  taskInstruction,
  onTaskInstructionChange,
  onSubmitTaskInstruction,
  onRunAction,
  runningTaskKey,
  hitlSetup,
  showHitlSetup,
  hitlRecipient,
  hitlDisplayName,
  hitlThreadKey,
  hitlConsentChecked,
  onRecipientChange,
  onDisplayNameChange,
  onThreadKeyChange,
  onConsentChange,
  onSaveHitlSetup,
  onSendHitlTest,
  savingHitl,
  sendingHitlTest,
}: {
  prompt: string;
  tasks: WorkspaceTask[];
  activeCount: number;
  waitingCount: number;
  selectedCandidateId: CandidateId | null;
  onSelectCandidate: (candidateId: CandidateId) => void;
  selectedQuery: string | null;
  taskInstruction: string;
  onTaskInstructionChange: (value: string) => void;
  onSubmitTaskInstruction: () => void;
  onRunAction: (action: string) => void;
  runningTaskKey: string | null;
  hitlSetup: HitlSetupResponse | null;
  showHitlSetup: boolean;
  hitlRecipient: string;
  hitlDisplayName: string;
  hitlThreadKey: string;
  hitlConsentChecked: boolean;
  onRecipientChange: (value: string) => void;
  onDisplayNameChange: (value: string) => void;
  onThreadKeyChange: (value: string) => void;
  onConsentChange: (value: boolean) => void;
  onSaveHitlSetup: () => void;
  onSendHitlTest: () => void;
  savingHitl: boolean;
  sendingHitlTest: boolean;
}) {
  return (
    <aside className="autobot-panel autobot-scrollbar flex min-h-[760px] flex-col overflow-hidden px-0 py-0">
      <div className="border-b border-white/7 px-5 py-4">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <span className="text-lg font-semibold text-slate-100">Tasks</span>
            <span className="text-lg font-semibold text-[#d3b15b]">{tasks.filter((task) => task.status === "review").length}</span>
            <span className="font-mono text-sm text-slate-400">1/{tasks.length}</span>
          </div>
        </div>
        <div className="mt-4 flex items-center gap-2">
          <span className="autobot-status" data-tone="success">{activeCount} active</span>
          <span className="autobot-status" data-tone="warning">{waitingCount} waiting</span>
        </div>
      </div>

      <div className="flex-1">
        {tasks.map((task) => (
          <div
            key={task.id}
            className={`flex items-center justify-between gap-3 border-b border-white/6 px-5 py-4 ${
              task.status === "review" ? "bg-white/3 shadow-[inset_2px_0_0_0_rgba(132,204,22,0.9)]" : ""
            }`}
          >
            <div className="min-w-0">
              <div className="flex items-center gap-3">
                <span
                  className={`size-2 rounded-full ${
                    task.status === "done"
                      ? "bg-[#74d86d]"
                      : task.status === "review"
                        ? "bg-[#d7b45c]"
                        : task.status === "active"
                          ? "bg-slate-300"
                          : "border border-slate-500"
                  }`}
                />
                <p className="truncate text-[15px] font-medium text-slate-100">{task.title}</p>
                {task.status === "review" ? (
                  <span className="autobot-status" data-tone="warning">
                    review
                  </span>
                ) : null}
              </div>
              <p className="mt-1 pl-5 text-sm text-slate-500">{task.subtitle}</p>
            </div>
            <span className="font-mono text-xs text-slate-500">{task.age}</span>
          </div>
        ))}
      </div>

      <div className="border-t border-white/7 px-5 py-4">
        <label className="autobot-label">Fire a task...</label>
        <div className="mt-3 flex items-center gap-2 rounded-[12px] border border-white/8 bg-black/25 px-3 py-2">
          <SendHorizontal className="size-4 text-[#79d165]" />
          <input
            value={taskInstruction}
            onChange={(event) => onTaskInstructionChange(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter") {
                event.preventDefault();
                onSubmitTaskInstruction();
              }
            }}
            className="w-full bg-transparent text-sm text-slate-300 outline-none"
          />
          <button
            onClick={onSubmitTaskInstruction}
            className="rounded-md border border-white/8 px-1.5 py-1 text-xs text-slate-400"
          >
            ↵
          </button>
        </div>
        <div className="mt-3 flex flex-wrap gap-2">
          {QUICK_ACTIONS.map((action) => (
            <button
              key={action}
              onClick={() => onRunAction(action)}
              className="rounded-md border border-white/8 bg-white/3 px-2.5 py-1.5 text-xs text-slate-400 transition hover:bg-white/6 hover:text-slate-200"
            >
              {runningTaskKey === action.toLowerCase().replaceAll(" ", "_") ? "running…" : action}
            </button>
          ))}
        </div>
        <div className="mt-4 flex items-center gap-2">
          {(["A", "B", "C"] as CandidateId[]).map((candidateId) => (
            <button
              key={candidateId}
              onClick={() => onSelectCandidate(candidateId)}
              className={`rounded-md border px-2.5 py-1.5 text-xs transition ${
                selectedCandidateId === candidateId
                  ? "border-[#72cf63]/50 bg-[#72cf63]/12 text-[#9be38f]"
                  : "border-white/8 bg-white/3 text-slate-400 hover:bg-white/6 hover:text-slate-200"
              }`}
            >
              candidate {candidateId}
            </button>
          ))}
        </div>

        {showHitlSetup ? (
          <PhotonSetupPanel
            hitlSetup={hitlSetup}
            recipient={hitlRecipient}
            displayName={hitlDisplayName}
            threadKey={hitlThreadKey}
            consentChecked={hitlConsentChecked}
            onRecipientChange={onRecipientChange}
            onDisplayNameChange={onDisplayNameChange}
            onThreadKeyChange={onThreadKeyChange}
            onConsentChange={onConsentChange}
            onSave={onSaveHitlSetup}
            onSendTest={onSendHitlTest}
            saving={savingHitl}
            sendingTest={sendingHitlTest}
          />
        ) : null}
      </div>
    </aside>
  );
}

function WorkspaceCanvas({
  candidate,
  render,
  detailMode,
  checkpoints,
  decisions,
  onDecision,
  onRecordClip,
  playback,
  onHoverComponent,
}: {
  candidate: RobotDesignCandidate | null;
  render: DesignSpecResponse["render"] | null;
  detailMode: DetailViewMode;
  checkpoints: DesignCheckpoint[];
  decisions: Partial<Record<string, CheckpointDecision>>;
  onDecision: (
    checkpointId: string,
    decision: Exclude<CheckpointDecision, "pending">,
  ) => void;
  onRecordClip: () => void;
  playback: {
    motion_profile: string;
    duration_s: number;
    provenance_summary: string;
  } | null;
  onHoverComponent: (component: EngineeringSceneNode | null) => void;
}) {
  return (
    <section className="relative flex min-h-[760px] flex-col gap-4">
      <div className="flex justify-center">
        <div className="flex w-full max-w-[620px] flex-col gap-4">
          {checkpoints.map((checkpoint, index) => (
            <motion.div
              key={checkpoint.id}
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.24, delay: index * 0.06 }}
            >
              <CheckpointCard
                checkpoint={checkpoint}
                decision={decisions[checkpoint.id] ?? "pending"}
                onDecision={(decision) => onDecision(checkpoint.id, decision)}
              />
            </motion.div>
          ))}
        </div>
      </div>

      <div className="autobot-panel relative flex-1 overflow-hidden">
        <div className="autobot-grid absolute inset-0 opacity-80" />
        <div className="absolute inset-0 bg-[radial-gradient(circle_at_top,rgba(132,204,22,0.08),transparent_24%),radial-gradient(circle_at_72%_18%,rgba(59,130,246,0.08),transparent_26%)]" />
        <div className="absolute inset-x-0 top-0 flex items-center justify-between px-6 py-4">
          <div>
            <p className="autobot-label">Current candidate</p>
            <h2 className="mt-2 text-[28px] font-semibold tracking-[-0.04em] text-slate-100">
              {candidate ? `Model ${candidate.candidate_id}` : "Resolving candidate"}
            </h2>
          </div>
          <div className="autobot-status" data-tone="muted">
            live morphology canvas
          </div>
        </div>

        <div className="absolute inset-x-8 bottom-7 top-20 overflow-hidden rounded-[16px] border border-white/7 bg-black/22">
          {candidate ? (
            <MorphologyViewer
              candidate={candidate}
              animated={true}
              mode={detailMode}
              renderGlb={render?.render_glb ?? null}
              uiScene={render?.ui_scene ?? null}
              onHoverComponent={onHoverComponent}
            />
          ) : (
            <div className="flex h-full items-center justify-center">
              <LoaderCircle className="size-8 animate-spin text-slate-500" />
            </div>
          )}
          <div className="pointer-events-none absolute inset-x-0 bottom-0 flex items-center justify-between border-t border-white/7 bg-black/35 px-5 py-4 text-sm text-slate-400">
            <span className="font-mono text-xs tracking-[0.2em]">100 mm</span>
            <div className="flex items-center gap-4">
              <span className="rounded-md border border-white/8 px-3 py-1 font-mono text-xs">00:04.2</span>
              <div className="flex items-center gap-2">
                <span className="h-1.5 w-10 rounded-full bg-slate-700" />
                <span className="h-1.5 w-8 rounded-full bg-[#79d165]" />
                <span className="h-1.5 w-6 rounded-full bg-slate-700" />
              </div>
              <span className="font-mono text-xs">1.0×</span>
              <button
                onClick={onRecordClip}
                className="rounded-md border border-white/8 px-3 py-1 text-xs text-slate-300"
              >
                record clip
              </button>
            </div>
          </div>
        </div>
        {playback ? (
          <div className="absolute left-8 top-24 max-w-sm rounded-md border border-white/8 bg-black/45 px-3 py-1.5 text-xs text-slate-300">
            <div>{playback.motion_profile} · {playback.duration_s.toFixed(1)} s</div>
            <div className="mt-1 text-[11px] text-slate-400">
              {playback.provenance_summary}
            </div>
          </div>
        ) : null}
      </div>
    </section>
  );
}

function InspectorPanel({
  candidate,
  telemetry,
  bom,
  plan,
  detailMode,
  onModeChange,
  inspectorTab,
  onTabChange,
  onContinue,
  continuing,
  selectedCandidateId,
  onSelectCandidate,
  exportsResponse,
  hoveredComponent,
}: {
  candidate: RobotDesignCandidate | null;
  telemetry: CandidateTelemetry | null;
  bom: BOMOutput | null;
  plan: Er16Plan | null;
  detailMode: DetailViewMode;
  onModeChange: (mode: DetailViewMode) => void;
  inspectorTab: InspectorTab;
  onTabChange: (tab: InspectorTab) => void;
  onContinue: () => void;
  continuing: boolean;
  selectedCandidateId: CandidateId | null;
  onSelectCandidate: (candidateId: CandidateId) => void;
  exportsResponse: DesignExportsResponse | null;
  hoveredComponent: EngineeringSceneNode | null;
}) {
  const actuatorRows = candidate ? buildActuatorRows(candidate, bom) : [];
  const alignmentRows = candidate && telemetry ? buildTaskAlignment(candidate, telemetry, plan) : [];
  const exportTargets = exportsResponse?.items ?? [];

  return (
    <aside className="autobot-panel flex min-h-[760px] flex-col px-5 py-5">
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="autobot-label">Candidate</p>
          <h3 className="mt-2 text-[28px] font-semibold tracking-[-0.04em] text-slate-100">
            {candidate ? `Serial ${countDof(candidate)}-DoF ${candidate.embodiment_class}` : "Awaiting candidate"}
          </h3>
          <p className="mt-2 max-w-[32ch] text-sm text-slate-400">
            {candidate?.rationale ?? "Waiting for candidate rationale."}
          </p>
        </div>
        <span className="autobot-label text-slate-500">{selectedCandidateId ? `candidate ${selectedCandidateId}` : "candidate"}</span>
      </div>

      <div className="mt-4 flex gap-2">
        <button
          onClick={() => onTabChange("spec")}
          className={`rounded-md border px-3 py-1.5 text-sm ${
            inspectorTab === "spec"
              ? "border-[#79d165]/35 bg-[#79d165]/10 text-[#a7e49f]"
              : "border-white/8 bg-white/3 text-slate-400"
          }`}
        >
          Spec
        </button>
        <button
          onClick={() => onTabChange("export")}
          className={`rounded-md border px-3 py-1.5 text-sm ${
            inspectorTab === "export"
              ? "border-[#79d165]/35 bg-[#79d165]/10 text-[#a7e49f]"
              : "border-white/8 bg-white/3 text-slate-400"
          }`}
        >
          Export
        </button>
        <button
          onClick={() => onTabChange("components")}
          className={`rounded-md border px-3 py-1.5 text-sm ${
            inspectorTab === "components"
              ? "border-[#79d165]/35 bg-[#79d165]/10 text-[#a7e49f]"
              : "border-white/8 bg-white/3 text-slate-400"
          }`}
        >
          Components
        </button>
      </div>

      <div className="mt-5 grid grid-cols-2 gap-2">
        {VIEW_MODES.map((mode) => (
          <button
            key={mode.id}
            onClick={() => onModeChange(mode.id)}
            className={`rounded-md border px-3 py-2 text-sm transition ${
              detailMode === mode.id
                ? "border-[#d9b15f]/45 bg-[#d9b15f]/12 text-[#efcb87]"
                : "border-white/8 bg-white/3 text-slate-400 hover:bg-white/6 hover:text-slate-200"
            }`}
          >
            {mode.label}
          </button>
        ))}
      </div>

      {inspectorTab === "spec" ? (
      <div className="mt-5 overflow-hidden rounded-[12px] border border-white/7">
        <table className="autobot-table text-sm">
          <thead>
            <tr>
              <th>Actuators</th>
              <th>Type</th>
              <th>T.</th>
              <th>Ratio</th>
            </tr>
          </thead>
          <tbody>
            {actuatorRows.map((row) => (
              <tr key={row.joint}>
                <td className="font-mono text-slate-400">{row.joint}</td>
                <td>{row.sku ? `${row.type} · ${row.sku}` : row.type}</td>
                <td>{row.torque}</td>
                <td>{row.ratio}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      ) : null}

      {inspectorTab === "spec" ? (
      <div className="mt-5">
        <p className="autobot-label">Task alignment</p>
        <div className="mt-3 space-y-3">
          {alignmentRows.map((row) => (
            <div key={row.label}>
              <div className="flex items-center justify-between gap-3 text-sm">
                <span className="text-slate-400">{row.label}</span>
                <span className="font-medium text-slate-100">{row.value}</span>
              </div>
              <div className="autobot-kpi-bar mt-2">
                <span style={{ width: `${Math.min(100, Math.max(8, row.progress * 100))}%` }} />
              </div>
            </div>
          ))}
        </div>
      </div>
      ) : null}

      {inspectorTab === "export" ? (
      <div className="mt-5">
        <p className="autobot-label">Export targets</p>
        <div className="mt-3 space-y-2">
          {exportTargets.map((target) => (
            <div
              key={target.label}
              className="flex items-center justify-between rounded-[10px] border border-white/7 bg-white/3 px-3 py-2"
            >
              <div className="min-w-0">
                <div className="flex items-center gap-3">
                  <span className="font-semibold text-slate-100">{target.label}</span>
                  <span className="text-sm text-slate-500">{target.subtitle}</span>
                </div>
              </div>
              <div className="flex items-center gap-2">
                <span className={`text-xs font-medium ${target.status === "ready" ? "text-[#8ee082]" : "text-slate-500"}`}>
                  {target.status}
                </span>
                <Download className="size-4 text-slate-500" />
              </div>
            </div>
          ))}
        </div>
      </div>
      ) : null}

      {inspectorTab === "components" ? (
      <div className="mt-5 space-y-3">
        <p className="autobot-label">Focused component</p>
        {hoveredComponent ? (
          <div className="rounded-[12px] border border-[#79d165]/20 bg-[#79d165]/[0.06] p-4">
            <div className="flex items-start justify-between gap-3">
              <div>
                <h4 className="text-base font-semibold text-slate-100">{hoveredComponent.display_name}</h4>
                <p className="mt-1 text-sm text-slate-400">{hoveredComponent.focus_summary}</p>
              </div>
              <span className="rounded-md border border-[#79d165]/30 px-2 py-1 text-[11px] uppercase tracking-[0.2em] text-[#9ce391]">
                {componentKindLabel(hoveredComponent.component_kind)}
              </span>
            </div>
            <dl className="mt-4 grid grid-cols-2 gap-3 text-sm">
              <div>
                <dt className="text-slate-500">Structure</dt>
                <dd className="mt-1 font-mono text-slate-200">{hoveredComponent.structure_id}</dd>
              </div>
              <div>
                <dt className="text-slate-500">Material</dt>
                <dd className="mt-1 text-slate-200">{hoveredComponent.material_label}</dd>
              </div>
              <div className="col-span-2">
                <dt className="text-slate-500">Envelope</dt>
                <dd className="mt-1 font-mono text-slate-200">
                  {hoveredComponent.bounds_m.map((value) => value.toFixed(3)).join(" × ")} m
                </dd>
              </div>
            </dl>
          </div>
        ) : (
          <div className="rounded-[12px] border border-white/7 bg-white/3 p-4 text-sm text-slate-400">
            Hover a structure in the live morphology canvas to inspect its material, envelope, and role.
          </div>
        )}
      </div>
      ) : null}

      <div className="mt-auto space-y-4 pt-6">
        <div className="grid grid-cols-3 gap-2">
          {(["A", "B", "C"] as CandidateId[]).map((candidateId) => (
            <button
              key={candidateId}
              onClick={() => onSelectCandidate(candidateId)}
              className={`rounded-md border px-3 py-2 text-sm transition ${
                selectedCandidateId === candidateId
                  ? "border-[#79d165]/45 bg-[#79d165]/12 text-[#a7e49f]"
                  : "border-white/8 bg-white/3 text-slate-400 hover:bg-white/6 hover:text-slate-200"
              }`}
            >
              Model {candidateId}
            </button>
          ))}
        </div>

        <Button
          onClick={onContinue}
          disabled={continuing || !candidate}
          className="h-11 w-full justify-between bg-[#72cf63] px-4 text-[#08110b] hover:bg-[#87dc79]"
        >
          {continuing ? (
            <>
              <span>Committing</span>
              <LoaderCircle className="size-4 animate-spin" />
            </>
          ) : (
            <>
              <span>Commit v3</span>
              <ArrowRight className="size-4" />
            </>
          )}
        </Button>
      </div>
    </aside>
  );
}

function PromptStage({
  prompt,
  setPrompt,
  submitting,
  onSubmit,
}: {
  prompt: string;
  setPrompt: (prompt: string) => void;
  submitting: boolean;
  onSubmit: () => void;
}) {
  return (
    <motion.section
      key="prompt"
      initial={{ opacity: 0, y: 18 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -12 }}
      transition={{ duration: 0.35, ease: "easeOut" }}
      className="flex flex-1 flex-col justify-center"
    >
      <div className="mx-auto flex w-full max-w-[1040px] flex-col items-center text-center">
        <div className="flex size-24 items-center justify-center rounded-[18px] border border-white/10 bg-white/4 shadow-[0_24px_80px_rgba(0,0,0,0.38)]">
          <Bot className="size-11 text-[#d9b15f]" />
        </div>
        <h1 className="mt-10 max-w-4xl text-balance text-[clamp(3.2rem,6vw,5.4rem)] font-semibold leading-[0.92] tracking-[-0.05em] text-slate-100">
          AutoBot builds the workspace around the robot, not around a dashboard.
        </h1>
        <p className="mt-6 max-w-2xl text-lg leading-8 text-slate-400">
          Describe the task. The app will synthesize candidates, surface approval checkpoints, and stage export-ready artifacts for review.
        </p>

        <div className="autobot-panel mt-12 w-full px-5 py-5">
          <label className="autobot-label flex items-center gap-2">
            <Sparkles className="size-4 text-[#79d165]" />
            Active prompt
          </label>
          <Textarea
            value={prompt}
            onChange={(event) => setPrompt(event.target.value)}
            placeholder='Describe the task, e.g. "Make a robot that can perform rock climbing and carry a rope pack on its back."'
            className="mt-4 min-h-[144px] resize-none border-0 bg-transparent px-0 py-0 text-lg text-slate-100 shadow-none focus-visible:ring-0"
          />
          <div className="mt-4 flex flex-wrap items-center justify-between gap-4">
            <div className="flex flex-wrap gap-2">
              {EXAMPLE_PROMPTS.map((example) => (
                <button
                  key={example}
                  onClick={() => setPrompt(example)}
                  className="rounded-md border border-white/8 bg-white/3 px-3 py-1.5 text-xs text-slate-400 transition hover:bg-white/6 hover:text-slate-200"
                >
                  {example}
                </button>
              ))}
            </div>
            <Button
              size="lg"
              onClick={onSubmit}
              disabled={submitting || !prompt.trim()}
              className="h-11 bg-[#d9b15f] px-5 text-[#0a0d10] hover:bg-[#e7c57c]"
            >
              {submitting ? (
                <>
                  <LoaderCircle className="size-4 animate-spin" />
                  Synthesizing
                </>
              ) : (
                <>
                  Build workspace
                  <ArrowRight className="size-4" />
                </>
              )}
            </Button>
          </div>
        </div>
      </div>
    </motion.section>
  );
}

export default function HomePage() {
  const router = useRouter();
  const [stage, setStage] = useState<WorkspaceStage>("prompt");
  const [prompt, setPrompt] = useState("");
  const [activePrompt, setActivePrompt] = useState("");
  const [plan, setPlan] = useState<Er16Plan | null>(null);
  const [ingestJobId, setIngestJobId] = useState<string | null>(null);
  const [referenceSourceType, setReferenceSourceType] = useState<string | null>(null);
  const [referencePayload, setReferencePayload] = useState<(Record<string, unknown> & { query?: unknown }) | null>(null);
  const [designs, setDesigns] = useState<GenerateDesignsResponse | null>(null);
  const [selectedCandidateId, setSelectedCandidateId] = useState<CandidateId | null>(null);
  const [detailMode, setDetailMode] = useState<DetailViewMode>("engineering");
  const [inspectorTab, setInspectorTab] = useState<InspectorTab>("spec");
  const [bomByCandidateId, setBomByCandidateId] = useState<Partial<Record<CandidateId, BOMOutput>>>({});
  const [specByCandidateId, setSpecByCandidateId] = useState<Partial<Record<CandidateId, DesignSpecResponse>>>({});
  const [checkpointsByCandidateId, setCheckpointsByCandidateId] = useState<Partial<Record<CandidateId, DesignCheckpoint[]>>>({});
  const [tasksByCandidateId, setTasksByCandidateId] = useState<Partial<Record<CandidateId, DesignTaskRun[]>>>({});
  const [exportsByCandidateId, setExportsByCandidateId] = useState<Partial<Record<CandidateId, DesignExportsResponse>>>({});
  const [playbackByCandidateId, setPlaybackByCandidateId] = useState<Partial<Record<CandidateId, {
    task_goal: string;
    motion_profile: string;
    duration_s: number;
    camera_mode: string;
    estimated_reach_m: number;
    candidate_id: CandidateId;
    source_type: "youtube_gvhmr" | "youtube_reference" | "droid_episode" | "droid_window" | "simulated_policy" | "unavailable";
    source_ready: boolean;
    source_ref: Record<string, unknown>;
    provenance_summary: string;
  }>>>({});
  const [submitting, setSubmitting] = useState(false);
  const [continuing, setContinuing] = useState(false);
  const [loadingBomCandidateId, setLoadingBomCandidateId] = useState<CandidateId | null>(null);
  const [runningTaskKey, setRunningTaskKey] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [hitlSetup, setHitlSetup] = useState<HitlSetupResponse | null>(null);
  const [showHitlSetup, setShowHitlSetup] = useState(false);
  const [hitlRecipientInput, setHitlRecipientInput] = useState("");
  const [hitlDisplayNameInput, setHitlDisplayNameInput] = useState("");
  const [hitlThreadKeyInput, setHitlThreadKeyInput] = useState("");
  const [hitlConsentChecked, setHitlConsentChecked] = useState(false);
  const [savingHitl, setSavingHitl] = useState(false);
  const [sendingHitlTest, setSendingHitlTest] = useState(false);
  const [taskInstruction, setTaskInstruction] = useState("");
  const [hoveredComponent, setHoveredComponent] = useState<EngineeringSceneNode | null>(null);

  const selectedDesignId = selectedCandidateId && designs ? designs.design_ids[selectedCandidateId] : null;
  const selectedSpec = selectedCandidateId ? specByCandidateId[selectedCandidateId] ?? null : null;
  const selectedCandidate = useMemo(
    () => selectedSpec?.design ?? designs?.candidates.find((candidate) => candidate.candidate_id === selectedCandidateId) ?? null,
    [designs, selectedCandidateId, selectedSpec],
  );
  const selectedTelemetry = selectedSpec?.telemetry ?? (selectedCandidateId ? designs?.candidate_telemetry[selectedCandidateId] ?? null : null);
  const selectedRender = selectedSpec?.render ?? (selectedCandidateId ? designs?.render_payloads[selectedCandidateId] ?? null : null);
  const selectedBom = selectedCandidateId ? bomByCandidateId[selectedCandidateId] ?? null : null;
  const workspaceTasks = useMemo(() => mapTaskRunsToWorkspaceTasks(
    selectedCandidateId ? tasksByCandidateId[selectedCandidateId] ?? [] : [],
  ), [selectedCandidateId, tasksByCandidateId]);
  const checkpoints = selectedCandidateId ? checkpointsByCandidateId[selectedCandidateId] ?? [] : [];
  const selectedExports = selectedCandidateId ? exportsByCandidateId[selectedCandidateId] ?? null : null;
  const selectedPlayback = selectedCandidateId ? playbackByCandidateId[selectedCandidateId] ?? null : null;
  const selectedQuery = typeof referencePayload?.query === "string" ? referencePayload.query : null;

  useEffect(() => {
    setTaskInstruction(selectedQuery ?? activePrompt ?? prompt);
  }, [selectedQuery, activePrompt, prompt, selectedCandidateId]);

  useEffect(() => {
    setHoveredComponent(null);
  }, [selectedCandidateId, detailMode]);

  function syncHitlInputs(setup: HitlSetupResponse | null) {
    const recipient = setup?.recipient;
    setHitlRecipientInput(recipient?.recipient ?? "");
    setHitlDisplayNameInput(recipient?.display_name ?? "");
    setHitlThreadKeyInput(recipient?.thread_key ?? "");
    setHitlConsentChecked(recipient?.consent_status === "confirmed");
    setShowHitlSetup(!setup?.can_send);
  }

  async function refreshHitlSetup() {
    const setup = await api.hitl.getSetup();
    setHitlSetup(setup);
    syncHitlInputs(setup);
    return setup;
  }

  function applyRuntimeEvent(candidateId: CandidateId, event: {
    event_type: string;
    data: Record<string, unknown>;
  }) {
    if (event.event_type === "task.created" || event.event_type === "task.updated") {
      if (!isDesignTaskRun(event.data)) return;
      const task = event.data;
      setTasksByCandidateId((current) => {
        const existing = current[candidateId] ?? [];
        const next = existing.filter((item) => item.id !== task.id);
        next.push(task);
        next.sort((left, right) => left.created_at.localeCompare(right.created_at));
        return { ...current, [candidateId]: next };
      });
      return;
    }
    if (event.event_type === "checkpoint.created" || event.event_type === "checkpoint.decided") {
      void api.designs.getCheckpoints(selectedDesignId ?? "").then((response) => {
        setCheckpointsByCandidateId((current) => ({ ...current, [candidateId]: response.items }));
      }).catch(() => {});
      return;
    }
    if (event.event_type === "revision.created") {
      const spec = (event.data.spec as DesignSpecResponse | undefined) ?? null;
      if (spec) {
        setSpecByCandidateId((current) => ({ ...current, [candidateId]: spec }));
        if (spec.bom) {
          setBomByCandidateId((current) => ({ ...current, [candidateId]: spec.bom as BOMOutput }));
        }
      }
      void api.designs.getExports(selectedDesignId ?? "").then((response) => {
        setExportsByCandidateId((current) => ({ ...current, [candidateId]: response }));
      }).catch(() => {});
      return;
    }
    if (event.event_type === "playback.ready") {
      if (isPlaybackPayload(event.data)) {
        setPlaybackByCandidateId((current) => ({ ...current, [candidateId]: event.data.playback }));
      }
    }
  }

  async function refreshDesignRuntime(candidateId: CandidateId, designId: string, options?: { includeTasks?: boolean }) {
    setLoadingBomCandidateId(candidateId);
    const [spec, checkpointsResponse, exportsResponse, tasksResponse] = await Promise.all([
      api.designs.getSpec(designId),
      api.designs.getCheckpoints(designId),
      api.designs.getExports(designId),
      options?.includeTasks ? api.designs.getTasks(designId) : Promise.resolve(null),
    ]);
    setSpecByCandidateId((current) => ({ ...current, [candidateId]: spec }));
    setCheckpointsByCandidateId((current) => ({ ...current, [candidateId]: checkpointsResponse.items }));
    if (tasksResponse) {
      setTasksByCandidateId((current) => ({ ...current, [candidateId]: tasksResponse.items }));
    } else {
      setTasksByCandidateId((current) => ({ ...current, [candidateId]: current[candidateId] ?? [] }));
    }
    setExportsByCandidateId((current) => ({ ...current, [candidateId]: exportsResponse }));
    if (spec.bom) {
      setBomByCandidateId((current) => ({ ...current, [candidateId]: spec.bom as BOMOutput }));
    } else {
      const bom = await api.designs.getBom(designId);
      setBomByCandidateId((current) => ({ ...current, [candidateId]: bom }));
    }
    setLoadingBomCandidateId((current) => (current === candidateId ? null : current));
  }

  useEffect(() => {
    if (!selectedCandidateId || !selectedDesignId) return;
    let cancelled = false;
    refreshDesignRuntime(selectedCandidateId, selectedDesignId)
      .catch((cause) => {
        if (cancelled) return;
        setError(cause instanceof Error ? cause.message : "Failed to load the design runtime.");
      });
    return () => {
      cancelled = true;
    };
  }, [selectedCandidateId, selectedDesignId]);

  useEffect(() => {
    if (!selectedCandidateId || !selectedDesignId) return;
    const url = `${API_BASE}/designs/${selectedDesignId}/events?follow=true&replay_delay_ms=160`;
    const source = new EventSource(url);
    const handleMessage = (event: MessageEvent<string>) => {
      try {
        const payload = JSON.parse(event.data) as { event_type: string; data: Record<string, unknown> };
        applyRuntimeEvent(selectedCandidateId, payload);
      } catch {
        // ignore malformed event
      }
    };
    source.addEventListener("task.created", handleMessage as EventListener);
    source.addEventListener("task.updated", handleMessage as EventListener);
    source.addEventListener("checkpoint.created", handleMessage as EventListener);
    source.addEventListener("checkpoint.decided", handleMessage as EventListener);
    source.addEventListener("revision.created", handleMessage as EventListener);
    source.addEventListener("playback.ready", handleMessage as EventListener);
    source.onerror = () => {
      source.close();
    };
    return () => {
      source.close();
    };
  }, [selectedCandidateId, selectedDesignId]);

  useEffect(() => {
    let cancelled = false;
    api.hitl
      .getSetup()
      .then((setup) => {
        if (cancelled) return;
        setHitlSetup(setup);
        syncHitlInputs(setup);
      })
      .catch((cause) => {
        if (cancelled) return;
        setError(cause instanceof Error ? cause.message : "Failed to load Photon setup.");
      });
    return () => {
      cancelled = true;
    };
  }, []);

  async function handleSaveHitlSetup() {
    const recipient = hitlRecipientInput.trim();
    if (!recipient) {
      setError("A phone number is required for Photon review polls.");
      return;
    }
    setSavingHitl(true);
    setError(null);
    try {
      let setup = await api.hitl.saveSetup({
        recipient,
        display_name: hitlDisplayNameInput.trim() || undefined,
        thread_key: hitlThreadKeyInput.trim() || undefined,
      });
      if (hitlConsentChecked && setup.recipient) {
        setup = await api.hitl.confirmSetup(setup.recipient.id);
      }
      setHitlSetup(setup);
      syncHitlInputs(setup);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Failed to save Photon setup.");
    } finally {
      setSavingHitl(false);
    }
  }

  async function handleSendHitlTest() {
    setSendingHitlTest(true);
    setError(null);
    try {
      await api.hitl.sendTest();
      await refreshHitlSetup();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Failed to send Photon test text.");
    } finally {
      setSendingHitlTest(false);
    }
  }

  async function handleSubmitPrompt() {
    const resolvedPrompt = prompt.trim();
    if (!resolvedPrompt) return;

    setSubmitting(true);
    setError(null);
    setStage("workspace");
    setActivePrompt(resolvedPrompt);
    setPlan(null);
    setDesigns(null);
    setSelectedCandidateId(null);
    setBomByCandidateId({});
    setSpecByCandidateId({});
    setCheckpointsByCandidateId({});
    setTasksByCandidateId({});
    setExportsByCandidateId({});
    setPlaybackByCandidateId({});
    setInspectorTab("spec");
    setHoveredComponent(null);

    try {
      const ingest = await api.ingest.start(resolvedPrompt);
      setPlan(ingest.er16_plan);
      setIngestJobId(ingest.job_id);
      setReferenceSourceType(ingest.reference_source_type ?? "youtube");
      setReferencePayload(ingest.reference_payload ?? null);
      await sleep(120);
      const generated = await api.designs.generate(ingest.job_id);
      setDesigns(generated);
      setSelectedCandidateId(generated.model_preferred_id);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Failed to assemble the design workspace.");
    } finally {
      setSubmitting(false);
    }
  }

  function selectCandidate(candidateId: CandidateId) {
    if (!designs) return;
    setSelectedCandidateId(candidateId);
    setHoveredComponent(null);
  }

  async function handleCheckpointDecision(
    checkpointId: string,
    decision: Exclude<CheckpointDecision, "pending">,
  ) {
    if (!selectedDesignId || !selectedCandidateId) return;
    setError(null);
    try {
      await api.designs.decideCheckpoint(selectedDesignId, checkpointId, decision);
      await refreshDesignRuntime(selectedCandidateId, selectedDesignId, { includeTasks: true });
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Failed to apply checkpoint decision.");
    }
  }

  async function runWorkspaceTask(action: string) {
    if (!selectedDesignId || !selectedCandidateId) return;
    if (action === "send review poll" && !hitlSetup?.can_send) {
      setShowHitlSetup(true);
      setError(
        hitlSetup?.provider_ready
          ? "Provide a phone number and confirm consent before sending Photon review polls."
          : "Configure Photon Spectrum credentials before sending Photon review polls.",
      );
      return;
    }
    const taskKeyMap: Record<string, string> = {
      "compare candidate B": "compare_candidate_b",
      "send review poll": "send_review_poll",
      "export URDF": "export_urdf",
      "cost BOM vs budget": "cost_bom_vs_budget",
    };
    const taskKey = taskKeyMap[action] ?? action.toLowerCase().replaceAll(" ", "_");
    setRunningTaskKey(taskKey);
    setError(null);
    try {
      await api.designs.runTask(selectedDesignId, taskKey);
      await refreshDesignRuntime(selectedCandidateId, selectedDesignId, { includeTasks: true });
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Failed to run task.");
    } finally {
      setRunningTaskKey(null);
    }
  }

  async function submitTaskInstruction() {
    if (!selectedDesignId || !selectedCandidateId || !taskInstruction.trim()) return;
    setRunningTaskKey("revise_design");
    try {
      const response = await api.designs.revise(selectedDesignId, taskInstruction.trim());
      setSpecByCandidateId((current) => ({ ...current, [selectedCandidateId]: response.spec }));
      if (response.spec.bom) {
        setBomByCandidateId((current) => ({ ...current, [selectedCandidateId]: response.spec.bom as BOMOutput }));
      }
      await refreshDesignRuntime(selectedCandidateId, selectedDesignId, { includeTasks: true });
      setError(null);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Failed to revise design.");
    } finally {
      setRunningTaskKey((current) => (current === "revise_design" ? null : current));
    }
  }

  async function handleRecordClip() {
    if (!selectedDesignId || !selectedCandidateId) return;
    setError(null);
    try {
      const result = await api.designs.recordClip(selectedDesignId);
      setPlaybackByCandidateId((current) => ({
        ...current,
        [selectedCandidateId]: result.playback,
      }));
      await refreshDesignRuntime(selectedCandidateId, selectedDesignId, { includeTasks: true });
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Failed to prepare playback.");
    }
  }

  async function continueToProgram() {
    if (!selectedDesignId || !ingestJobId || !selectedCandidateId) return;
    setContinuing(true);
    setError(null);
    try {
      const evolution = await api.evolutions.create(`workspace-${Date.now()}`, ingestJobId);
      await api.designs.select(selectedDesignId, evolution.evolution_id);
      router.push(
        `/evolutions/${evolution.evolution_id}/program?draft=${encodeURIComponent(
          evolution.draft_content,
        )}&design=${selectedCandidateId}`,
      );
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Failed to open the program draft.");
    } finally {
      setContinuing(false);
    }
  }

  return (
    <LayoutGroup>
      <main className="min-h-screen px-5 py-5 text-slate-100 md:px-6">
        <div className="mx-auto max-w-[1720px]">
          <div className="autobot-shell overflow-hidden px-5 py-4 md:px-6">
            <header className="flex flex-wrap items-center justify-between gap-4 border-b border-white/7 pb-4">
              <div className="flex items-center gap-4">
                <div className="flex items-center gap-3">
                  <span className="flex items-center gap-2 text-sm font-semibold text-slate-100">
                    <Bot className="size-4 text-[#d9b15f]" />
                    AutoBot
                  </span>
                  <span className="text-slate-600">/</span>
                  <span className="text-sm text-slate-400">orchard_01</span>
                </div>
              </div>
              <div className="flex items-center gap-2">
                <span className="autobot-status" data-tone="success">
                  3 active
                </span>
                <span className="autobot-status" data-tone="warning">
                  2 waiting
                </span>
                <span className="autobot-status" data-tone="muted">
                  AV
                </span>
              </div>
            </header>

            {error ? (
              <div className="mt-4 flex items-start gap-3 rounded-[12px] border border-red-400/20 bg-red-500/10 px-4 py-3 text-sm text-red-100">
                <TriangleAlert className="mt-0.5 size-4 shrink-0" />
                <span>{error}</span>
              </div>
            ) : null}

            <AnimatePresence mode="wait">
              {stage === "prompt" ? (
                <PromptStage
                  prompt={prompt}
                  setPrompt={setPrompt}
                  submitting={submitting}
                  onSubmit={handleSubmitPrompt}
                />
              ) : (
                <motion.section
                  key="workspace"
                  initial={{ opacity: 0, y: 16 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0, y: -12 }}
                  transition={{ duration: 0.28 }}
                  className="pt-5"
                >
                  <div className="autobot-panel mb-5 px-5 py-4">
                    <div className="flex items-start justify-between gap-4">
                      <div className="min-w-0">
                        <p className="autobot-label">Active task</p>
                        <h1 className="mt-2 text-balance text-[22px] font-semibold tracking-[-0.03em] text-slate-100">
                          {activePrompt || "Synthesizing robot workspace..."}
                        </h1>
                        <div className="mt-3 flex flex-wrap gap-2">
                          <span className="rounded-md border border-white/8 bg-white/3 px-2.5 py-1 text-xs text-slate-400">
                            Reference source: {referenceSourceType ?? "pending"}
                          </span>
                          {selectedQuery ? (
                            <span className="rounded-md border border-white/8 bg-white/3 px-2.5 py-1 text-xs text-slate-400">
                              query: {selectedQuery}
                            </span>
                          ) : null}
                          {(plan?.affordances ?? []).slice(0, 3).map((item) => (
                            <span
                              key={item}
                              className="rounded-md border border-white/8 bg-white/3 px-2.5 py-1 text-xs text-slate-400"
                            >
                              {item}
                            </span>
                          ))}
                        </div>
                      </div>
                      <Button
                        variant="outline"
                        className="border-white/10 bg-white/3 text-slate-200 hover:bg-white/6"
                        onClick={() => setStage("prompt")}
                      >
                        <PencilLine className="size-4" />
                        Edit prompt
                      </Button>
                    </div>
                  </div>

                  <div className="grid gap-5 xl:grid-cols-[320px_minmax(0,1fr)_360px]">
                    <TaskRail
                      prompt={activePrompt}
                      tasks={workspaceTasks}
                      activeCount={workspaceTasks.filter((task) => task.status === "active" || task.status === "done").length}
                      waitingCount={workspaceTasks.filter((task) => task.status === "waiting" || task.status === "review").length}
                      selectedCandidateId={selectedCandidateId}
                      onSelectCandidate={selectCandidate}
                      selectedQuery={selectedQuery}
                      taskInstruction={taskInstruction}
                      onTaskInstructionChange={setTaskInstruction}
                      onSubmitTaskInstruction={submitTaskInstruction}
                      onRunAction={runWorkspaceTask}
                      runningTaskKey={runningTaskKey}
                      hitlSetup={hitlSetup}
                      showHitlSetup={showHitlSetup}
                      hitlRecipient={hitlRecipientInput}
                      hitlDisplayName={hitlDisplayNameInput}
                      hitlThreadKey={hitlThreadKeyInput}
                      hitlConsentChecked={hitlConsentChecked}
                      onRecipientChange={setHitlRecipientInput}
                      onDisplayNameChange={setHitlDisplayNameInput}
                      onThreadKeyChange={setHitlThreadKeyInput}
                      onConsentChange={setHitlConsentChecked}
                      onSaveHitlSetup={handleSaveHitlSetup}
                      onSendHitlTest={handleSendHitlTest}
                      savingHitl={savingHitl}
                      sendingHitlTest={sendingHitlTest}
                    />

                    <WorkspaceCanvas
                      candidate={selectedCandidate}
                      render={selectedRender}
                      detailMode={detailMode}
                      checkpoints={checkpoints}
                      decisions={Object.fromEntries(
                        checkpoints.map((checkpoint) => [checkpoint.id, checkpoint.decision]),
                      )}
                      onDecision={handleCheckpointDecision}
                      onRecordClip={handleRecordClip}
                      playback={selectedPlayback}
                      onHoverComponent={(component) => {
                        setHoveredComponent(component);
                        if (component && detailMode === "components") {
                          setInspectorTab("components");
                        }
                      }}
                    />

                    <InspectorPanel
                      candidate={selectedCandidate}
                      telemetry={selectedTelemetry}
                      bom={selectedBom}
                      plan={plan}
                      detailMode={detailMode}
                      onModeChange={setDetailMode}
                      inspectorTab={inspectorTab}
                      onTabChange={setInspectorTab}
                      onContinue={continueToProgram}
                      continuing={continuing}
                      selectedCandidateId={selectedCandidateId}
                      onSelectCandidate={selectCandidate}
                      exportsResponse={selectedExports}
                      hoveredComponent={hoveredComponent}
                    />
                  </div>

                  <div className="mt-5 grid gap-4 lg:grid-cols-[minmax(0,1fr)_340px]">
                    <div className="autobot-panel-soft px-4 py-3">
                      <div className="flex items-center justify-between gap-4">
                        <div className="min-w-0">
                          <p className="autobot-label">Selected candidate summary</p>
                          <p className="mt-2 text-sm text-slate-300">
                            {selectedCandidate ? topologyLabel(selectedCandidate) : "candidate pending"} ·
                            {" "}cost {telemetryCostChip(selectedTelemetry)} ·
                            {" "}mass {selectedTelemetry?.estimated_mass_kg.toFixed(1) ?? "0.0"} kg
                          </p>
                        </div>
                        {loadingBomCandidateId ? (
                          <span className="autobot-status" data-tone="muted">
                            loading BOM
                          </span>
                        ) : (
                          <span className="autobot-status" data-tone="success">
                            BOM cached
                          </span>
                        )}
                      </div>
                    </div>

                    <div className="autobot-panel-soft flex items-center justify-between gap-3 px-4 py-3">
                      <div className="flex items-center gap-2 text-sm text-slate-400">
                        <ShieldCheck className="size-4 text-[#79d165]" />
                        export bundle staging
                      </div>
                      <div className="flex items-center gap-2">
                        <Cable className="size-4 text-slate-500" />
                        <Package2 className="size-4 text-slate-500" />
                        <ClipboardCheck className="size-4 text-slate-500" />
                        <Component className="size-4 text-slate-500" />
                        <Orbit className="size-4 text-slate-500" />
                      </div>
                    </div>
                  </div>
                </motion.section>
              )}
            </AnimatePresence>
          </div>
        </div>
      </main>
    </LayoutGroup>
  );
}
