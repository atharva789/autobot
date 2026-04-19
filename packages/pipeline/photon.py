"""Photon-facing HITL message and poll payloads.

The transport is intentionally configurable so the app can be wired to the
actual Photon/Spectrum runtime without coupling the backend to a specific
deployment shape.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
import json
import os
from pathlib import Path
import subprocess
from typing import Any, Protocol

import httpx

from packages.pipeline.telemetry import CandidateTelemetry


@dataclass(frozen=True)
class PhotonPollOption:
    label: str
    value: str
    description: str | None = None


@dataclass(frozen=True)
class PhotonDispatchResult:
    ok: bool
    payload: dict[str, Any]
    message_id: str | None = None
    raw_response: dict[str, Any] | None = None


@dataclass(frozen=True)
class PhotonTextDraft:
    recipient: str
    text: str
    thread_key: str | None = None


@dataclass(frozen=True)
class PhotonPollDraft:
    design_id: str
    question: str
    options: list[PhotonPollOption]
    thread_key: str | None = None
    summary: str | None = None


class PhotonTransport(Protocol):
    def send_text(
        self,
        *,
        recipient: str,
        text: str,
        thread_key: str | None = None,
    ) -> PhotonDispatchResult: ...

    def send_poll(
        self,
        *,
        recipient: str,
        question: str,
        options: list[PhotonPollOption],
        thread_key: str | None = None,
    ) -> PhotonDispatchResult: ...


class HttpPhotonTransport:
    """Very small HTTP transport for Photon-compatible dispatch endpoints."""

    def __init__(
        self,
        base_url: str,
        *,
        api_key: str | None = None,
        timeout_s: float = 10.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout_s = timeout_s

    def _post(self, path: str, payload: dict[str, Any]) -> PhotonDispatchResult:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        with httpx.Client(timeout=self.timeout_s) as client:
            response = client.post(f"{self.base_url}{path}", json=payload, headers=headers)
        raw: dict[str, Any]
        try:
            raw = response.json()
        except ValueError:
            raw = {"text": response.text}
        return PhotonDispatchResult(
            ok=response.is_success,
            payload=payload,
            raw_response=raw,
            message_id=raw.get("message_id") or raw.get("id"),
        )

    def send_text(
        self,
        *,
        recipient: str,
        text: str,
        thread_key: str | None = None,
    ) -> PhotonDispatchResult:
        return self._post(
            "/messages",
            {
                "recipient": recipient,
                "thread_key": thread_key,
                "text": text,
                "kind": "text",
            },
        )

    def send_poll(
        self,
        *,
        recipient: str,
        question: str,
        options: list[PhotonPollOption],
        thread_key: str | None = None,
    ) -> PhotonDispatchResult:
        return self._post(
            "/polls",
            {
                "recipient": recipient,
                "thread_key": thread_key,
                "question": question,
                "options": [option.__dict__ for option in options],
                "kind": "poll",
            },
        )


class SpectrumCliPhotonTransport:
    """Dispatch through a Node CLI that uses the real Spectrum SDK."""

    def __init__(
        self,
        script_path: str | Path,
        *,
        node_executable: str = "node",
        timeout_s: float = 20.0,
        extra_env: dict[str, str] | None = None,
    ) -> None:
        self.script_path = Path(script_path)
        self.node_executable = node_executable
        self.timeout_s = timeout_s
        self.extra_env = extra_env or {}

    def _run(self, payload: dict[str, Any]) -> PhotonDispatchResult:
        if not self.script_path.exists():
            raise RuntimeError(f"Spectrum CLI script not found: {self.script_path}")
        env = os.environ.copy()
        env.update(self.extra_env)
        proc = subprocess.run(
            [self.node_executable, str(self.script_path)],
            input=json.dumps(payload),
            text=True,
            capture_output=True,
            timeout=self.timeout_s,
            cwd=str(self.script_path.parent.parent),
            env=env,
            check=False,
        )
        if proc.returncode != 0:
            stderr = proc.stderr.strip() or proc.stdout.strip() or "unknown Spectrum CLI error"
            raise RuntimeError(stderr)
        try:
            raw = json.loads(proc.stdout)
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"Spectrum CLI returned invalid JSON: {proc.stdout}") from exc
        return PhotonDispatchResult(
            ok=bool(raw.get("ok", True)),
            payload=payload,
            raw_response=raw,
            message_id=raw.get("message_id") or raw.get("id"),
        )

    def send_text(
        self,
        *,
        recipient: str,
        text: str,
        thread_key: str | None = None,
    ) -> PhotonDispatchResult:
        return self._run(
            {
                "kind": "text",
                "recipient": recipient,
                "text": text,
                "thread_key": thread_key,
            }
        )

    def send_poll(
        self,
        *,
        recipient: str,
        question: str,
        options: list[PhotonPollOption],
        thread_key: str | None = None,
    ) -> PhotonDispatchResult:
        return self._run(
            {
                "kind": "poll",
                "recipient": recipient,
                "question": question,
                "thread_key": thread_key,
                "options": [option.__dict__ for option in options],
            }
        )


def build_design_review_text(
    *,
    title: str,
    summary: str,
    value_delta: str,
    footer: str | None = None,
) -> str:
    parts = [title, summary, value_delta]
    if footer:
        parts.append(footer)
    return "\n".join(part.strip() for part in parts if part.strip())


def _normalize_poll_options(options: Iterable[str | PhotonPollOption]) -> list[PhotonPollOption]:
    normalized: list[PhotonPollOption] = []
    for option in options:
        if isinstance(option, PhotonPollOption):
            normalized.append(option)
        else:
            slug = str(option).lower().strip()
            slug = slug.replace("...", "")
            slug = slug.replace(".", "")
            slug = slug.replace(" ", "_")
            normalized.append(
                PhotonPollOption(label=str(option), value=slug)
            )
    return normalized


def build_design_review_poll(
    *,
    design_id: str,
    candidate_id: str,
    title: str,
    summary: str,
    options: Iterable[str | PhotonPollOption],
    thread_key: str | None = None,
) -> PhotonPollDraft:
    normalized = _normalize_poll_options(options)
    question = f"{title}: {summary}"
    return PhotonPollDraft(
        design_id=design_id,
        question=question,
        options=normalized,
        thread_key=thread_key,
        summary=f"Model {candidate_id} approval decision",
    )


@dataclass
class PhotonMessenger:
    transport: PhotonTransport

    def send_text(
        self,
        *,
        recipient: str,
        text: str,
        thread_key: str | None = None,
    ) -> PhotonDispatchResult:
        return self.transport.send_text(
            recipient=recipient,
            text=text,
            thread_key=thread_key,
        )

    def send_poll(
        self,
        *,
        recipient: str,
        question: str,
        options: list[PhotonPollOption],
        thread_key: str | None = None,
    ) -> PhotonDispatchResult:
        return self.transport.send_poll(
            recipient=recipient,
            question=question,
            options=options,
            thread_key=thread_key,
        )

    def send_design_review(
        self,
        *,
        recipient: str,
        design_id: str,
        candidate_id: str,
        telemetry: CandidateTelemetry,
        thread_key: str | None = None,
    ) -> PhotonDispatchResult:
        poll = build_design_review_poll(
            design_id=design_id,
            candidate_id=candidate_id,
            title="Approve design checkpoint",
            summary=telemetry.summary,
            options=["Approve", "Deny", "Guide..."],
            thread_key=thread_key,
        )
        return self.send_poll(
            recipient=recipient,
            question=poll.question,
            options=poll.options,
            thread_key=thread_key,
        )


def photon_provider_ready() -> bool:
    project_id = os.environ.get("PHOTON_PROJECT_ID", "").strip()
    secret = os.environ.get("PHOTON_SECRET_KEY", "").strip()
    base_url = os.environ.get("PHOTON_BASE_URL", "").strip()
    return bool((project_id and secret) or base_url)


def build_photon_messenger_from_env() -> PhotonMessenger:
    project_id = os.environ.get("PHOTON_PROJECT_ID", "").strip()
    secret = os.environ.get("PHOTON_SECRET_KEY", "").strip()
    if project_id and secret:
        script_path = (
            Path(__file__).resolve().parents[2]
            / "apps"
            / "web"
            / "scripts"
            / "photon_send.mjs"
        )
        return PhotonMessenger(
            transport=SpectrumCliPhotonTransport(
                script_path=script_path,
            )
        )

    base_url = os.environ.get("PHOTON_BASE_URL", "").strip()
    if base_url:
        return PhotonMessenger(
            transport=HttpPhotonTransport(
                base_url=base_url,
                api_key=os.environ.get("PHOTON_API_KEY", "").strip() or None,
            )
        )

    raise RuntimeError(
        "Photon is not configured. Set PHOTON_PROJECT_ID and PHOTON_SECRET_KEY "
        "for Spectrum delivery, or PHOTON_BASE_URL for the local HTTP shim."
    )
