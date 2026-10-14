# Forever AI contributor guidance

Read README.md and docs/pipeline.md before changes. This project is a macOS /
Windows desktop companion and a WoW: Forever addon, not a website. The public
source repository is https://github.com/szh101/Forever-companion-.git.
Fetch and preserve remote changes; use task branches and never force-push.
Do not copy another repository's Git history into this independent repository.

Keep shared files free of personal names, computer names, real home or game
installation paths, account emails, private installation records, credentials,
screenshots and conversations. Use environment variables or generic placeholders.
Keep machine-specific evidence in ignored local runtime files. README.md is the
English homepage; keep README.zh-CN.md installation and usage instructions
equivalent. Before publishing, review tracked content and commit identity; use a
GitHub noreply email instead of a personal email. A clean current tree does not
establish clean Git history.

Read docs/windows-development-handoff.md before Windows development. Reuse the
shared provider, snapshot and addon code; keep platform capture and packaging
separate. Preserve the other platform's behavior. The compact Tk chat window is
320 x 380 logical pixels with 10-point chat/input fonts, icon buttons, adjustable
opacity and a separate settings window. Windows passive scrolling and background
click-through must preserve game keyboard control. Do not migrate to a Web UI
without an explicit product decision.

Keep game access read-only. Capture only a WoW window after the user enables
automatic capture or explicitly clicks the one-shot screenshot button. If no
window is selected, that button may detect and select the first WoW window; no
detected window means no capture. Never fall back to desktop capture, inject
code, read game memory, synthesize game input, or bypass secret/protected values.
Addon exports are user-initiated. Never execute model output, clipboard text or
Lua SavedVariables as code. Credentials and transcripts must not be persisted by
the companion. API-path screenshots stay in memory. Codex CLI image input may
use a private per-request temporary file, with guaranteed normal/error/timeout
cleanup and documented forced-termination limits. Never inspect or copy CLI
auth files/tokens.

Codex-generated images may be read only from the official artifact directory for
the exact thread ID emitted by this invocation, with new-file timestamps,
bounded decoding and link rejection. Never scan other threads, accept a
model-selected artifact root, or read auth/history files. Preserve CLI-owned
originals and document that Codex itself may retain generated image artifacts.

Use only the official authenticated Codex CLI bridge, isolated and ephemeral,
with shell, plugins, computer use and user MCP/config disabled. No unauthenticated
HTTP proxy. Do not route Claude subscription OAuth through this third-party app;
Claude uses its official API key. Use one natural-language chat flow; do not
require a text/source-image/generated-image mode selector. The model may choose
an image tool when a request calls for a new illustration. API chat offers only
the configured image connection and executes at most one image call per turn;
never fall back to another paid provider automatically. Source pictures require
public HTTPS targets, bounded decoding and no credentials on image downloads.

Provider contract tests and Lua mock tests do not establish real macOS / Windows
capture, live API access, client compatibility, or Blizzard approval. Report
these separately. Validate the exact source snapshot being published according
to docs/pipeline.md. Keep Python/Lua checks and the macOS native build check;
do not remove platform checks to make another platform's run pass.

Mac builds use ScreenCaptureKit for a selected local WoW window; never request
Screen Recording on startup. Only the user-facing permission button may request
that permission. Hidden checks use synthetic data and mock clipboard/model/game
access. Visible UI and game validation require a suitable user-approved testing
session. When a user is playing, follow their current restrictions: do not steal
focus, send input, capture the game or restart applications in the background.
