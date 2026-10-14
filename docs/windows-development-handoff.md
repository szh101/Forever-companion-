# Windows development guide

macOS and Windows share [Forever-companion-](https://github.com/szh101/Forever-companion-).
Read AGENTS.md, the [README](../README.md), [publication checks](pipeline.md) and
[verification status](verification.md) before development. Use a separate working
directory or task branch and preserve changes for both platforms.

The current prototype is companion 0.4.3 with addon 0.3.0. Keep the compact Tk
chat window, separate settings, icon controls and one natural-language chat flow.
The main window is 320 x 380 logical pixels. Enter inserts a newline and
Shift+Enter sends. Directly pasted `/fai` JSON is validated and imported, with
clear feedback that preserves the question draft and never echoes raw clipboard
contents. Windows passive overlay behavior must preserve keyboard control until
the user clicks the input field, and return control on the first click back to
the previously focused game window. See [Windows behavior](windows.md).

## Platform ownership

| Path | Responsibility |
| --- | --- |
| `companion/app.py`, `companion/ui_icons.py` | Shared Tk chat, settings and icon controls |
| `companion/core.py`, `companion/providers.py` | Snapshot validation, provider contracts and model presets |
| `companion/local_codex.py` | Official CLI bridge, isolation, login checks and temporary attachments |
| `companion/reply_images.py`, `companion/image_tools.py` | Bounded image downloads and configured image tools |
| `companion/capture.py`, `native/WindowsCapture.cs` | Windows window identification and Graphics Capture |
| `companion/windows_overlay.py`, `companion/overlay_ui.py` | Passive Windows interaction and Tk event routing |
| `companion/clipboard_image.py` | Bounded clipboard image encoding and writes after explicit capture |
| `companion/mac_capture.py`, `native/MacCapture.swift` | macOS ScreenCaptureKit bridge |
| `companion/windows_ui.py`, `companion/windows_files.py` | Windows display scaling and image-path validation |
| `addon/ForeverAI/` | Shared read-only Lua addon and user-initiated `/fai` export |
| `scripts/build_windows.py`, `scripts/windows_entry.py`, `native/windows.manifest` | Fixed-source Windows packaging and hidden executable self-test |
| `scripts/build_macos.py`, `scripts/build_native.py` | Fixed-source macOS packaging and native compilation |
| `scripts/check.py`, `tests/` | Offline Python and Lua contract checks |
| `scripts/windows_quiet.py`, `scripts/gui_smoke.py` | Background and hidden GUI checks |

## Constraints to preserve

- Reuse shared contracts rather than creating separate provider or snapshot
  implementations for Windows. Keep capture and packaging platform-specific.
- Screenshot capture is off by default. Explicit one-shot capture may detect the
  first WoW window if none is selected; failure never falls back to the desktop.
- Use the official Codex CLI with its existing login, isolated ephemeral calls
  and no shell, plugins, computer use or user MCP/config. Never inspect or copy
  authentication files. Claude uses its official API key, not subscription OAuth.
- Keep provider credentials and chat data in memory. The bounded per-request
  Codex image-file exception and CLI-owned generated images have explicit cleanup
  and retention limits documented in the README.
- Preserve public-HTTPS-only image downloads, decoding limits, generated artifact
  directory validation and Windows junction/hard-link rejection.
- Do not request live model calls, read real clipboard data, capture a game or
  operate the desktop as part of offline checks. A prior development session's
  authorization does not establish permission to operate a new user's machine.

## Validation and publication

Follow [background checks](windows-test-handoff.md) before visible testing. Read
the final JSON report; never treat a started process as a passed test. Current
evidence is summarized in [Windows verification](windows-verification.md).

Shared UI changes still require macOS regression and native build checks; keep
those pending when only Windows is available. Preserve the macOS checks in
`.ai-pipeline.json`. Source publication, binary packaging, installation, live
provider requests and game compatibility are separate outcomes. Update the
relevant documentation with actual results and remaining limitations, without
publishing machine-specific paths, private history or installation receipts.
