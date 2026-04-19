from __future__ import annotations

import json
import os
import subprocess
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from packages.pipeline.photon import (
    HttpPhotonTransport,
    PhotonPollOption,
    SpectrumCliPhotonTransport,
    PhotonTransport,
    build_design_review_poll,
    build_design_review_text,
    PhotonDispatchResult,
)


class _FakeTransport(PhotonTransport):
    def __init__(self) -> None:
        self.sent_texts: list[dict] = []
        self.sent_polls: list[dict] = []

    def send_text(self, *, recipient: str, text: str, thread_key: str | None = None):
        payload = {"recipient": recipient, "text": text, "thread_key": thread_key}
        self.sent_texts.append(payload)
        return PhotonDispatchResult(ok=True, payload=payload)

    def send_poll(
        self,
        *,
        recipient: str,
        question: str,
        options: list[PhotonPollOption],
        thread_key: str | None = None,
    ):
        payload = {
            "recipient": recipient,
            "question": question,
            "options": [option.model_dump() for option in options],
            "thread_key": thread_key,
        }
        self.sent_polls.append(payload)
        return PhotonDispatchResult(ok=True, payload=payload)


def test_build_design_review_poll_uses_robot_delta_language():
    poll = build_design_review_poll(
        design_id="design-1",
        candidate_id="A",
        title="Approve actuator J2 shoulder",
        summary="Harmonic drive selected over cycloidal. Stiffness +22%, backlog <= 0.1°, cost +$180.",
        options=["Approve", "Deny", "Guide..."],
    )

    assert poll.question.startswith("Approve")
    assert poll.options[0].label == "Approve"
    assert poll.options[-1].value == "guide"
    assert poll.design_id == "design-1"


def test_build_design_review_text_is_concise_and_specific():
    text = build_design_review_text(
        title="Confirm payload budget",
        summary="Compliant wrist adds 340g at the end-effector.",
        value_delta="New total payload budget: 1.84 kg.",
    )

    assert "Confirm payload budget" in text
    assert "1.84 kg" in text
    assert "340g" in text


def test_http_photon_transport_posts_real_json_to_local_server():
    captured: list[dict] = []

    class _Handler(BaseHTTPRequestHandler):
        def do_POST(self):  # noqa: N802
            length = int(self.headers.get("Content-Length", "0"))
            raw = self.rfile.read(length)
            captured.append(
                {
                    "path": self.path,
                    "headers": dict(self.headers.items()),
                    "body": json.loads(raw.decode("utf-8")),
                }
            )
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"message_id":"msg-local"}')

        def log_message(self, format, *args):  # noqa: A003
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    try:
        transport = HttpPhotonTransport(
            base_url=f"http://127.0.0.1:{server.server_address[1]}",
            api_key="photon-test-key",
        )

        text_result = transport.send_text(
            recipient="+15551234567",
            text="Robot design A ready for review",
            thread_key="orchard-01",
        )
        poll_result = transport.send_poll(
            recipient="+15551234567",
            question="Approve design checkpoint?",
            options=[
                PhotonPollOption(label="Approve", value="approve"),
                PhotonPollOption(label="Deny", value="deny"),
            ],
            thread_key="orchard-01",
        )
    finally:
        server.shutdown()
        server.server_close()

    assert text_result.ok is True
    assert text_result.message_id == "msg-local"
    assert poll_result.ok is True
    assert poll_result.message_id == "msg-local"
    assert len(captured) == 2
    assert captured[0]["path"] == "/messages"
    assert captured[0]["headers"]["Authorization"] == "Bearer photon-test-key"
    assert captured[0]["body"]["kind"] == "text"
    assert captured[0]["body"]["recipient"] == "+15551234567"
    assert captured[1]["path"] == "/polls"
    assert captured[1]["body"]["kind"] == "poll"
    assert captured[1]["body"]["options"][0]["label"] == "Approve"


def test_spectrum_cli_transport_invokes_real_node_script_in_mock_mode():
    repo_root = Path(__file__).resolve().parents[1]
    script_path = repo_root / "apps" / "web" / "scripts" / "photon_send.mjs"
    assert script_path.exists(), "Spectrum bridge script must exist"

    transport = SpectrumCliPhotonTransport(
        script_path=script_path,
        node_executable="node",
        timeout_s=15.0,
        extra_env={
            "PHOTON_MOCK_MODE": "1",
            "PHOTON_PROJECT_ID": "project-demo",
            "PHOTON_SECRET_KEY": "secret-demo",
        },
    )

    text_result = transport.send_text(
        recipient="+15551234567",
        text="Spectrum mock hello",
        thread_key="iMessage;-;+15551234567",
    )
    poll_result = transport.send_poll(
        recipient="+15551234567",
        question="Approve J2 actuator?",
        options=[
            PhotonPollOption(label="Approve", value="approve"),
            PhotonPollOption(label="Deny", value="deny"),
        ],
        thread_key="iMessage;-;+15551234567",
    )

    assert text_result.ok is True
    assert text_result.message_id == "mock-text-message"
    assert text_result.raw_response["transport"] == "spectrum-cli-mock"
    assert text_result.raw_response["space_id"] == "iMessage;-;+15551234567"

    assert poll_result.ok is True
    assert poll_result.message_id == "mock-poll-message"
    assert poll_result.raw_response["transport"] == "spectrum-cli-mock"
    assert poll_result.raw_response["space_id"] == "iMessage;-;+15551234567"
    assert poll_result.raw_response["options"] == ["Approve", "Deny"]


def test_spectrum_cli_script_fails_cleanly_without_configuration():
    repo_root = Path(__file__).resolve().parents[1]
    script_path = repo_root / "apps" / "web" / "scripts" / "photon_send.mjs"
    payload = json.dumps(
        {
            "kind": "text",
            "recipient": "+15551234567",
            "text": "hello",
        }
    )

    result = subprocess.run(
        ["node", str(script_path)],
        input=payload,
        text=True,
        capture_output=True,
        cwd=repo_root / "apps" / "web",
        env={
            key: value
            for key, value in os.environ.items()
            if key not in {"PHOTON_PROJECT_ID", "PHOTON_SECRET_KEY", "PHOTON_MOCK_MODE"}
        },
        check=False,
    )

    assert result.returncode != 0
    assert "PHOTON_PROJECT_ID and PHOTON_SECRET_KEY" in result.stderr
