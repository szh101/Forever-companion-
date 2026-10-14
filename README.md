# Forever AI · WoW Forever Assistant

**English** | [简体中文](README.zh-CN.md)

Forever AI combines a read-only game AddOn with a desktop chat Companion. Share a snapshot of your character, equipment and quests with AI to ask about drops, recipes or quest order, optionally adding a game screenshot.

Replies appear in the desktop chat window. **Chatting with AI inside the game's chat channels is not currently supported.** The desktop interface is in English; AI replies follow the language of your question.

This is a development prototype: Companion **0.4.3**, AddOn **0.3.0**. The AddOn uses TOC **16001** for the corresponding WoW: Forever client; compatibility with other retail, Classic or beta clients is not guaranteed.

## Which download should I choose?

**Windows 10 (2004+) / 11 x64: [download ForeverAI-Setup-x64.exe](https://github.com/szh101/Forever-companion-/releases/latest/download/ForeverAI-Setup-x64.exe).** One setup wizard installs the desktop Companion and game AddOn. Python and the screenshot helper are included; no source download or compilation is needed.

1. Run **`ForeverAI-Setup-x64.exe`** and choose English or Simplified Chinese.
2. Keep the AddOn option selected and choose the **Forever client folder containing `Wow.exe` or `WowClassic.exe`**. Select the client you actually play, not the Battle.net launcher folder. You can skip the AddOn if you only want the Companion.
3. Finish installation and open **Forever AI** from the Start menu or desktop shortcut.
4. On the next full game launch, enable **Forever AI | Snapshot** in the AddOns list. Continue with [Connect AI](#3-connect-ai), then [Ask your first question](#4-ask-your-first-question).

You still need your own model account or API key. The installer does not log in for you or restart the game. The installer is unsigned; Windows may show an unknown-publisher or reputation notice.

When updating the AddOn, setup preserves its previous folder in the client's `Interface/ForeverAI-backups`. Uninstalling the Companion leaves the game AddOn and these backups in place.

Other downloads are on the [Releases page](https://github.com/szh101/Forever-companion-/releases):

| Download | Use it for |
| --- | --- |
| **`ForeverAI-Setup-x64.exe`** | Recommended Windows installation, including the optional AddOn. |
| `ForeverAI-Windows-x64-<commit>.zip` | Portable Windows app. Keep the entire `Forever AI` folder and launch `Forever AI.exe`; install the included AddOn manually. |
| `ForeverAI-AddOn-*.zip` | Game AddOn only; extract `ForeverAI` into the client's `Interface/AddOns` folder. |
| `SHA256SUMS.txt` | Checksums for the release downloads. |

**macOS:** a Mac installer is not included in this Windows release. Use the [macOS source instructions](#macos) below. GitHub's **Code → Download ZIP** and automatic **Source code (zip / tar.gz)** downloads are for source installation and development.

## 1. Install the game AddOn

**The Windows installer can do this for you.** These manual steps are for portable, AddOn-only and source downloads.

1. Locate the **Forever client you actually launch**, then open its `Interface/AddOns` directory. A folder name such as `_retail_`, `_classic_` or `_classic_beta_` alone does not establish compatibility.
2. Copy the entire **`ForeverAI`** folder from the AddOn ZIP, or **`addon/ForeverAI`** from the portable/source download, into it. Before a manual update, you can back up the old AddOn outside the game directory.
3. Check this layout. There must not be an extra nested folder:

```text
<your Forever client>/Interface/AddOns/ForeverAI/
├── ForeverAI.toc
├── ForeverAI.lua
└── Snapshot.lua
```

4. For a **first installation**, fully quit and restart the game. Enable **Forever AI | Snapshot** in the character selection screen's AddOns list. When updating an already loaded AddOn, you can usually run `/reload` manually instead.
5. Enter the game and type **`/fai`** while out of combat. The copy panel confirms that the AddOn loaded.

If the AddOn is missing, check the selected client version, installation path and all three files above. Starting the Companion itself does not install the AddOn.

## 2. Start the desktop Companion

**Installer users:** open Forever AI from its shortcut and continue to [Connect AI](#3-connect-ai). The following source instructions are optional for Windows and currently required for macOS. Installing source dependencies requires internet access.

### Windows source installation (optional)

Download and extract the source from **Code → Download ZIP**, or clone it:

```sh
git clone https://github.com/szh101/Forever-companion-.git
cd Forever-companion-
```

1. Install [Python 3.11 or newer](https://www.python.org/downloads/windows/) with **Tcl/Tk** and the **Python launcher**. An x64 installation is recommended.
2. In the fully extracted project folder, double-click **`setup-windows.cmd`** and wait for dependency installation. This creates a project-local `.venv`.
3. Double-click **`start-windows.cmd`** to open the Companion. Use the same file on subsequent launches; setup is only needed once.

These steps enable snapshot-based chat. **Source setup does not automatically compile the live window capture helper.** To enable that feature, install the required .NET Framework reference assemblies and Windows metadata, then run this from the project folder:

```powershell
.venv\Scripts\python.exe scripts\build_windows_capture.py
```

If the build dependencies or capture helper are unavailable, you can still use AddOn snapshots or import a PNG/JPEG game screenshot in the Companion's settings. See the [Windows guide](docs/windows.md) for further build details.

### macOS

Download and extract the source using **Code → Download ZIP**. Install [Python 3.11 or newer](https://www.python.org/downloads/macos/) with **Tcl/Tk**. In Terminal, enter the extracted project directory and run:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m companion.app
```

For later launches, run only the last line. If `_tkinter` is missing, use a Python installation that includes Tcl/Tk and recreate the virtual environment.

Live window capture requires **macOS 14+** and the Swift capture helper. After installing Xcode Command Line Tools, run:

```sh
.venv/bin/python scripts/build_native.py
```

With `.venv` and the Swift toolchain installed, you can also launch with `zsh start-mac.command`; it compiles the helper first if missing. Screen Recording permission is requested only when you click the permission button in the Companion. You can skip the native build and permission setup if you do not use capture.

## 3. Connect AI

Open the **gear icon** and choose a connection:

| Connection | What you need |
| --- | --- |
| **Offline demo** | No account. Displays fictional text and a diagram to check the interface, without calling a model. |
| **Codex (signed in)** | Install the official Codex CLI yourself and sign in with your own ChatGPT account. The Companion uses that CLI and your account's limits; you do not enter an API key in the Companion. |
| **OpenAI / Gemini / Claude** | An API key from the selected provider. Choose a model or enter a model ID your account can access. Billing and limits are controlled by that provider. |

**Installing the Codex desktop app, including its Microsoft Store version, does not guarantee that the official CLI is installed or available to the Companion.** Follow the [official Codex CLI installation instructions](https://learn.chatgpt.com/docs/codex/cli) and [authentication guide](https://learn.chatgpt.com/docs/auth), then use the connection check in the Companion's settings. The check does not send a model request. If it reports unsupported isolation options, update the CLI at the path shown in the error.

Keys remain only in the Companion's memory for the current run, so you must enter them again after restarting. Use your own account or key and never commit credentials to GitHub. The Claude connection uses an API key, not the Claude desktop app's login or subscription credentials. Chat and image model availability depends on your account and provider.

## 4. Ask your first question

1. Type **`/fai`** in the game. The panel prepares and selects the snapshot data.
2. Press **Ctrl+C** on Windows or **Command+C** on Mac (or Ctrl+C if supported by your client). The AddOn cannot write directly to the system clipboard, so you must press the shortcut yourself.
3. Click **Paste AddOn snapshot** in the Companion, or paste the data directly into the input box. Wait for **Import successful** and the quest count, then enter your question.
4. Press **Shift+Enter to send**; **Enter inserts a newline**. Try “Suggest an order for my quests that reduces travel,” “Where does this item drop?” or “How can I obtain this recipe?”
5. Export and paste again when your character's state changes; snapshots do not sync in real time. Open the relevant bank, profession or NPC window before exporting if you need that information.

Each import replaces the entire snapshot. Unloaded or restricted data is marked unknown or partial; this is not a complete game database. AI can use web search where supported by the selected connection; the current Gemini connection does not enable web search. There is no built-in comprehensive Forever loot or recipe database, and suggested routes are not guaranteed to be optimal.

Chat supports text, public guide images and generated diagrams. Click an image to enlarge it; Esc closes the preview. API image generation requires a configured OpenAI or Gemini image connection; Claude chat needs a separate image provider. The current API flow does not offer image generation tools when a screenshot is attached. Codex uses its own available image tools and does not automatically switch to another paid API. See the [architecture guide](docs/architecture.md).

## Screenshots and window controls

Capture is off by default. In settings, select a PNG/JPEG file or select a local WoW window for preview and capture. On Windows and macOS, the **Capture & paste** icon beside Paste AddOn captures the selected game window, copies the image to the clipboard and attaches it to the next question. If no window is selected, it detects and selects the first WoW window; if none is found, it captures nothing. When running multiple clients, choose the intended window in settings.

A successful capture turns off automatic capture before every message. Attachments expire after two minutes and must be captured again. If the clipboard is busy, the image remains available as an attachment. Capture failures never fall back to the entire desktop.

The current source offers a compact chat window, icon buttons, collapse/expand and pin controls. Settings can adjust the main window's opacity from 45% to 100% for the current run. On Windows, drag the upper-left handle to move the window or the lower-right handle to resize it. The chat area supports scrolling, and background clicks pass through.

Click the input box to type. Moving the pointer outside still allows typing; clicking the previous game window ends input while preserving unsent text. Sending a message or pressing Esc in the input box also attempts to return focus to the previous window. Settings and image previews use ordinary windows. Actual interaction still needs verification across clients and display environments; automated checks do not replace in-game acceptance testing.

## Data handling and game boundaries

- The AddOn reads through accessible game UI APIs and exports snapshots at your request. It does not read game memory, automate your character, or collect private messages, mail bodies or friends/guild rosters. Other players' equipment is limited to data made available after you manually inspect them.
- A normal AddOn cannot send HTTP requests, launch local applications or connect to MCP. The external Companion handles networking and AI requests. Replies are not written back into game chat.
- When you send a question, the selected model service receives the question, imported snapshot and any attached image. Requests replay only the last four text turns. Screenshots can include character names or chat visible on screen; choose what you send.
- The Companion does not persist keys, chats or downloaded guide images. Regular API images stay in memory. **Codex image inputs** briefly use a private per-request temporary directory, cleaned after normal completion, errors or timeouts; forcibly terminating the application may leave temporary files. Screenshots you explicitly copy to the system clipboard are managed by the operating system.
- Codex itself may retain images it generates. The Companion reads only new images from the current invocation, not other conversations, authentication files or login tokens. Account and server-side retention policies belong to the provider.
- Public guide image downloads carry no API key, cookies or login information. Only HTTPS images passing address, size and pixel limits are accepted. AI output is never executed as code or game commands.

This project has not received Blizzard approval or compliance certification. See the [snapshot guide](docs/snapshot.md) for fields, availability conditions and access limitations.

## Development and documentation

Development checks use locked dependencies:

```sh
uv sync --locked --group dev
uv run --locked --group dev python scripts/check.py
uv run --locked python scripts/gui_smoke.py
```

Standalone builds use a fixed Git commit: `scripts/build_windows.py` on Windows or `scripts/build_macos.py` on Mac, each with `--commit FULL_COMMIT_SHA` and the appropriate platform toolchain. Build artifacts and runtime data are not committed to Git.

The release source passed 155 automated Windows checks with one platform-dependent check skipped, plus hidden UI and packaged application checks. The macOS contract suite passed 150 checks with six platform-specific skips, and its native capture helper compiled. Installation and update checks use a synthetic game directory. These checks do not exercise a running game, live AI requests or the visible macOS interface.

- [Architecture and integration boundaries](docs/architecture.md)
- [Snapshot coverage and limitations](docs/snapshot.md)
- [Windows use and packaging](docs/windows.md)
- [Checks and publication workflow](docs/pipeline.md)
- [Verification scope](docs/verification.md) · [Windows verification notes](docs/windows-verification.md)

The detailed technical documents use a mix of English and Chinese.
