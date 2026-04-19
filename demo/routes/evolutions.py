from __future__ import annotations
import difflib
import json
import logging
import os
import tempfile
import time
import uuid
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel

from demo.supabase_client import supa
from demo.workspace_store import workspace_store
from demo.services.evolution_service import EvolutionService
from demo.services.orchestrator import CLIOrchestrator
from demo.services.modal_dispatch import ModalDispatch
from packages.pipeline.types import EvolutionConfig

router = APIRouter(prefix="/evolutions", tags=["evolutions"])
_evo_svc = EvolutionService(store=workspace_store)
_dispatch = ModalDispatch()
logger = logging.getLogger(__name__)

TEMPLATE_DIR = Path("data/artifacts/evolutions/template")
ARTIFACTS_DIR = Path(
    os.environ.get(
        "EVOLUTION_ARTIFACTS_DIR",
        str(Path(tempfile.gettempdir()) / "il_ideation" / "evolutions"),
    )
)


class CreateEvolutionRequest(BaseModel):
    run_id: str
    ingest_job_id: str


class ApproveProgramRequest(BaseModel):
    content: str


@router.post("", status_code=201)
def create_evolution(req: CreateEvolutionRequest) -> dict:
    stage = "create_evolution"
    try:
        evo_id = _evo_svc.create(run_id=req.run_id)
        workdir = ARTIFACTS_DIR / evo_id
        workdir.mkdir(parents=True, exist_ok=True)
        if TEMPLATE_DIR.exists():
            for f in ["prepare.py", "train.py", "morphology_factory.py"]:
                src = TEMPLATE_DIR / f
                if src.exists():
                    (workdir / f).write_text(src.read_text())
        orch = CLIOrchestrator(workdir=workdir)
        stage = "load_ingest_plan"
        ingest = workspace_store.get_ingest_job(req.ingest_job_id)
        if ingest is None:
            raise HTTPException(status_code=404, detail="Ingest job not found")
        plan = json.loads(ingest["er16_plan_json"])
        stage = "draft_program_md"
        draft, generator = orch.draft_program_md(er16_plan=plan)
        draft_id = str(uuid.uuid4())
        stage = "persist_draft"
        workspace_store.save_program_draft({
            "id": draft_id,
            "evolution_id": evo_id,
            "generator": generator,
            "draft_content": draft,
            "approved": False,
        })
        return {"evolution_id": evo_id, "draft_id": draft_id, "draft_content": draft}
    except Exception as exc:
        logger.exception("Evolution creation failed at stage=%s", stage)
        raise HTTPException(
            status_code=502,
            detail={"stage": stage, "error": str(exc)},
        ) from exc


@router.post("/{evo_id}/approve-program")
def approve_program(
    evo_id: str, req: ApproveProgramRequest, bg: BackgroundTasks
) -> dict:
    workdir = ARTIFACTS_DIR / evo_id
    workdir.mkdir(parents=True, exist_ok=True)
    (workdir / "program.md").write_text(req.content)
    workspace_store.update_program_draft_by_evolution(
        evo_id,
        {"approved": True, "user_edited_content": req.content},
    )
    _evo_svc.update_status(evo_id, "running")
    bg.add_task(_run_evolution_loop, evo_id)
    return {"status": "running"}


@router.post("/{evo_id}/stop")
def stop_evolution(evo_id: str) -> dict:
    _evo_svc.update_status(evo_id, "stopped")
    return {"status": "stopped"}


@router.post("/{evo_id}/mark-best/{iter_id}")
def mark_best(evo_id: str, iter_id: str) -> dict:
    _evo_svc.set_best(evo_id, iter_id)
    return {"best_iteration_id": iter_id}


@router.get("/{evo_id}")
def get_evolution(evo_id: str) -> dict:
    evolution = _evo_svc.get(evo_id)
    if evolution is None:
        raise HTTPException(status_code=404, detail="Evolution not found")
    return evolution


def _run_evolution_loop(evo_id: str) -> None:
    cfg = EvolutionConfig()
    workdir = ARTIFACTS_DIR / evo_id
    orch = CLIOrchestrator(workdir=workdir)

    evo = _evo_svc.get(evo_id)
    try:
        run = (
            supa.table("runs")
            .select("clip_id")
            .eq("id", evo["run_id"])
            .single()
            .execute()
        )
        clip = (
            supa.table("clips")
            .select("smpl_path")
            .eq("id", run.data["clip_id"])
            .single()
            .execute()
        )
        smpl_url = clip.data["smpl_path"]
    except Exception:
        smpl_url = ""

    try:
        best_score = -float("inf")
        no_improve = 0
        t0 = time.time()

        for i in range(cfg.max_iters):
            evo_fresh = _evo_svc.get(evo_id)
            if evo_fresh["status"] in ("stopped", "done", "failed"):
                return   # user stopped or already terminal — do NOT overwrite status
            if (time.time() - t0) / 3600 >= cfg.max_hours:
                break

            train_py = (
                (workdir / "train.py").read_text()
                if (workdir / "train.py").exists()
                else ""
            )
            morph_py = (
                (workdir / "morphology_factory.py").read_text()
                if (workdir / "morphology_factory.py").exists()
                else ""
            )

            context = (
                f"program.md:\n{(workdir / 'program.md').read_text()}\n"
                if (workdir / "program.md").exists()
                else ""
            )
            orch.edit_files(
                prompt=context + f"Iteration {i}. Improve train.py and/or morphology_factory.py.",
                editable=["train.py", "morphology_factory.py"],
            )

            try:
                result = _dispatch.run_trial(
                    evolution_id=evo_id,
                    iter_num=i,
                    train_py_source=(
                        (workdir / "train.py").read_text()
                        if (workdir / "train.py").exists()
                        else ""
                    ),
                    morph_factory_source=(
                        (workdir / "morphology_factory.py").read_text()
                        if (workdir / "morphology_factory.py").exists()
                        else ""
                    ),
                    smpl_trajectory_url=smpl_url,
                )
            except Exception as exc:
                supa.table("iterations").insert({
                    "id": str(uuid.uuid4()),
                    "evolution_id": evo_id,
                    "iter_num": i,
                    "fitness_score": 0.0,
                    "reasoning_log": f"Trial failed: {exc}",
                }).execute()
                continue

            new_train = (
                (workdir / "train.py").read_text()
                if (workdir / "train.py").exists()
                else ""
            )
            new_morph = (
                (workdir / "morphology_factory.py").read_text()
                if (workdir / "morphology_factory.py").exists()
                else ""
            )
            train_diff = "".join(
                difflib.unified_diff(
                    train_py.splitlines(keepends=True),
                    new_train.splitlines(keepends=True),
                )
            )
            morph_diff = "".join(
                difflib.unified_diff(
                    morph_py.splitlines(keepends=True),
                    new_morph.splitlines(keepends=True),
                )
            )

            iter_id = _evo_svc.record_iteration(
                evo_id,
                i,
                {
                    "fitness_score": result.fitness_score,
                    "tracking_error": result.tracking_error,
                    "er16_success_prob": result.er16_success_prob,
                    "replay_mp4_url": result.replay_mp4_url,
                    "controller_ckpt_url": result.controller_ckpt_url,
                    "trajectory_npz_url": result.trajectory_npz_url,
                    "reasoning_log": result.reasoning_md,
                    "train_py_diff": train_diff,
                    "morph_factory_diff": morph_diff,
                },
            )

            if result.fitness_score > best_score + cfg.keep_best_threshold:
                best_score = result.fitness_score
                _evo_svc.set_best(evo_id, iter_id)
                no_improve = 0
            else:
                no_improve += 1

            if no_improve >= 5:
                break

        # Only mark done if still running (not stopped by user)
        evo_final = _evo_svc.get(evo_id)
        if evo_final["status"] == "running":
            _evo_svc.update_status(evo_id, "done")
    except Exception as exc:
        _evo_svc.update_status(evo_id, "failed")
        raise
