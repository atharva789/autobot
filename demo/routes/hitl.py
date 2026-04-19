from __future__ import annotations

import os
import uuid

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from demo.workspace_store import workspace_store
from packages.pipeline.photon import (
    PhotonMessenger,
    build_photon_messenger_from_env,
    build_design_review_text,
    photon_provider_ready,
)
from packages.pipeline.schemas import CandidateTelemetry

router = APIRouter(prefix="/hitl", tags=["hitl"])


class PhotonSendRequest(BaseModel):
    recipient: str | None = None
    thread_key: str | None = None


class PhotonTextRequest(PhotonSendRequest):
    text: str | None = None


class PhotonSetupRequest(BaseModel):
    recipient: str
    display_name: str | None = None
    thread_key: str | None = None


class PhotonConfirmRequest(BaseModel):
    recipient_id: str


def _build_messenger() -> PhotonMessenger:
    if not photon_provider_ready():
        raise HTTPException(
            status_code=503,
            detail=(
                "Photon is not configured. Set PHOTON_PROJECT_ID and PHOTON_SECRET_KEY "
                "for Spectrum delivery, or PHOTON_BASE_URL for the local HTTP shim."
            ),
        )
    try:
        return build_photon_messenger_from_env()
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


def _resolve_recipient(requested: str | None) -> str:
    if requested:
        recipient = requested.strip()
        if recipient:
            return recipient
    stored = workspace_store.get_default_hitl_recipient("photon")
    if stored and stored.get("recipient"):
        return str(stored["recipient"]).strip()
    recipient = os.environ.get("PHOTON_RECIPIENT", "").strip()
    if not recipient:
        raise HTTPException(
            status_code=400,
            detail="A Photon recipient is required either in the request or PHOTON_RECIPIENT.",
        )
    return recipient


@router.get("/setup")
def get_hitl_setup() -> dict:
    recipient = workspace_store.get_default_hitl_recipient("photon")
    provider_ready = photon_provider_ready()
    consent_confirmed = bool(recipient and recipient.get("consent_status") == "confirmed")
    return {
        "provider_ready": provider_ready,
        "recipient": recipient,
        "can_send": provider_ready and consent_confirmed,
    }


@router.post("/setup", status_code=201)
def save_hitl_setup(req: PhotonSetupRequest) -> dict:
    existing = workspace_store.get_default_hitl_recipient("photon")
    if existing is not None:
        workspace_store.update_hitl_recipient(
            existing["id"],
            {
                "recipient": req.recipient,
                "display_name": req.display_name,
                "thread_key": req.thread_key,
                "consent_status": "pending",
                "is_default": True,
            },
        )
        recipient = workspace_store.get_hitl_recipient(existing["id"])
    else:
        recipient = workspace_store.upsert_hitl_recipient(
            {
                "id": str(uuid.uuid4()),
                "channel": "photon",
                "recipient": req.recipient,
                "display_name": req.display_name,
                "thread_key": req.thread_key,
                "consent_status": "pending",
                "is_default": True,
            }
        )
    return {
        "recipient": recipient,
        "provider_ready": photon_provider_ready(),
        "can_send": False,
    }


@router.post("/setup/confirm")
def confirm_hitl_setup(req: PhotonConfirmRequest) -> dict:
    recipient = workspace_store.get_hitl_recipient(req.recipient_id)
    if not recipient:
        raise HTTPException(status_code=404, detail="Photon recipient not found")
    workspace_store.update_hitl_recipient(
        req.recipient_id,
        {
            "consent_status": "confirmed",
            "is_default": True,
        },
    )
    updated = workspace_store.get_hitl_recipient(req.recipient_id)
    provider_ready = photon_provider_ready()
    return {
        "recipient": updated,
        "provider_ready": provider_ready,
        "can_send": provider_ready and updated is not None and updated.get("consent_status") == "confirmed",
    }


@router.post("/setup/test")
def send_test_text(req: PhotonSendRequest) -> dict:
    messenger = _build_messenger()
    recipient = _resolve_recipient(req.recipient)
    result = messenger.send_text(
        recipient=recipient,
        text="Photon setup confirmed. Future robot review checkpoints will be delivered here.",
        thread_key=req.thread_key,
    )
    return {
        "ok": result.ok,
        "message_id": result.message_id,
        "payload": result.payload,
        "raw_response": result.raw_response,
    }


@router.post("/designs/{design_id}/poll")
def send_design_poll(design_id: str, req: PhotonSendRequest) -> dict:
    design = workspace_store.get_design(design_id)
    if not design:
        raise HTTPException(status_code=404, detail="Design not found")

    telemetry = design.get("telemetry_json")
    if not telemetry:
        raise HTTPException(
            status_code=400,
            detail="Design telemetry is required before sending a Photon poll.",
        )

    messenger = _build_messenger()
    recipient = _resolve_recipient(req.recipient)
    telemetry_model = CandidateTelemetry.model_validate(telemetry)
    result = messenger.send_design_review(
        recipient=recipient,
        design_id=design_id,
        candidate_id=str(design["candidate_id"]),
        telemetry=telemetry_model,
        thread_key=req.thread_key,
    )
    return {
        "ok": result.ok,
        "message_id": result.message_id,
        "payload": result.payload,
        "raw_response": result.raw_response,
    }


@router.post("/designs/{design_id}/text")
def send_design_text(design_id: str, req: PhotonTextRequest) -> dict:
    design = workspace_store.get_design(design_id)
    if not design:
        raise HTTPException(status_code=404, detail="Design not found")

    telemetry = design.get("telemetry_json")
    if not telemetry:
        raise HTTPException(
            status_code=400,
            detail="Design telemetry is required before sending a Photon text.",
        )

    messenger = _build_messenger()
    recipient = _resolve_recipient(req.recipient)
    summary = telemetry["summary"] if isinstance(telemetry, dict) else str(telemetry)
    text = req.text or build_design_review_text(
        title=f"Robot design {design['candidate_id']} ready for review",
        summary=summary,
        value_delta=f"Cost {telemetry['estimated_total_cost_usd']} | Mass {telemetry['estimated_mass_kg']} kg",
        footer="Reply with approval, changes, or a follow-up question.",
    )
    result = messenger.send_text(
        recipient=recipient,
        text=text,
        thread_key=req.thread_key,
    )
    return {
        "ok": result.ok,
        "message_id": result.message_id,
        "payload": result.payload,
        "raw_response": result.raw_response,
    }
