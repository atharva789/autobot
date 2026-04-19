import { readFile } from "node:fs/promises";
import { stdin as input, stdout, stderr, env } from "node:process";

import { Spectrum } from "spectrum-ts";
import { imessage } from "spectrum-ts/providers/imessage";
import { chatGuid } from "@photon-ai/advanced-imessage";

async function readStdin() {
  const chunks = [];
  for await (const chunk of input) {
    chunks.push(Buffer.from(chunk));
  }
  return Buffer.concat(chunks).toString("utf8");
}

function writeJson(value) {
  stdout.write(`${JSON.stringify(value)}\n`);
}

function fail(message, detail) {
  const error = detail ? `${message}: ${detail}` : message;
  stderr.write(`${error}\n`);
  process.exit(1);
}

async function resolveSpace(app, recipient, threadKey) {
  if (threadKey && threadKey.trim()) {
    return threadKey.trim();
  }
  const provider = imessage(app);
  const user = await provider.user(recipient);
  const space = await provider.space([user]);
  return space.id;
}

function getRemoteClient(app) {
  return app?.__internal?.platforms?.get("iMessage")?.client?.[0] ?? null;
}

async function main() {
  const raw = await readStdin();
  const payload = JSON.parse(raw || "{}");

  if (env.PHOTON_MOCK_MODE === "1") {
    const spaceId = payload.thread_key?.trim() || `iMessage;-;${payload.recipient}`;
    writeJson({
      ok: true,
      transport: "spectrum-cli-mock",
      kind: payload.kind,
      space_id: spaceId,
      recipient: payload.recipient,
      thread_key: payload.thread_key ?? null,
      message_id: payload.kind === "poll" ? "mock-poll-message" : "mock-text-message",
      options: Array.isArray(payload.options) ? payload.options.map((option) => option.label ?? option) : [],
    });
    return;
  }

  const projectId = env.PHOTON_PROJECT_ID?.trim();
  const projectSecret = env.PHOTON_SECRET_KEY?.trim();
  if (!projectId || !projectSecret) {
    fail("PHOTON_PROJECT_ID and PHOTON_SECRET_KEY must be configured");
  }

  const app = await Spectrum({
    projectId,
    projectSecret,
    providers: [imessage.config()],
  });

  try {
    const spaceId = await resolveSpace(app, String(payload.recipient ?? "").trim(), payload.thread_key);
    if (payload.kind === "text") {
      await app.send({ id: spaceId, __platform: "iMessage" }, String(payload.text ?? ""));
      writeJson({
        ok: true,
        transport: "spectrum-cli",
        kind: "text",
        message_id: `text:${Date.now()}`,
        space_id: spaceId,
      });
      return;
    }

    if (payload.kind === "poll") {
      const client = getRemoteClient(app);
      if (!client?.polls?.create) {
        fail("Spectrum iMessage poll support is unavailable for the configured runtime");
      }
      const receipt = await client.polls.create(
        chatGuid(spaceId),
        String(payload.question ?? ""),
        Array.isArray(payload.options) ? payload.options.map((option) => option.label ?? String(option)) : [],
      );
      writeJson({
        ok: true,
        transport: "spectrum-cli",
        kind: "poll",
        message_id: receipt?.guid ?? `poll:${Date.now()}`,
        space_id: spaceId,
      });
      return;
    }

    fail(`Unsupported dispatch kind ${payload.kind}`);
  } finally {
    await app.stop().catch(() => {});
  }
}

main().catch((error) => fail("Photon Spectrum dispatch failed", error instanceof Error ? error.message : String(error)));
