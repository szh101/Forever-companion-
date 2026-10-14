"""Private stdio bridge to the user's official Codex CLI; no token extraction."""
from __future__ import annotations

import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import time

from .core import Answer, ReplyImage, SYSTEM, UserError, build_request
from .reply_images import decode_image, extract_images, normalize_image
from .windows_files import artifact_stream, linked_path, linked_windows_ancestor

CODEX_PROVIDER = "Codex（已登录）"
AUTO_MODEL = "自动（Codex 默认）"
REQUIRED_FLAGS = ("--ignore-user-config", "--ephemeral", "--json")
DISABLED_FEATURES = (
    "shell_tool", "unified_exec", "apps", "plugins", "hooks", "computer_use",
    "browser_use", "browser_use_external", "browser_use_full_cdp_access", "in_app_browser",
    "code_mode", "code_mode_only", "multi_agent", "multi_agent_v2",
    "view_image", "memories", "skill_search", "skill_mcp_dependency_install",
    "workspace_dependencies", "remote_plugin", "goals", "sleep_tool",
)


def windows_codex_candidates():
    """Find CLI binaries installed by Codex without depending on Explorer's PATH.

    Only inspect the application's bin/<version>/codex.exe layout, never its
    user data. Version directory names are hashes, so prefer the newest file.
    """
    roots = [Path.home() / "AppData/Local"]
    if os.environ.get("LOCALAPPDATA"):
        roots.insert(0, Path(os.environ["LOCALAPPDATA"]))
    found = {}
    for root in dict.fromkeys(roots):
        try:
            for candidate in (root / "OpenAI/Codex/bin").glob("*/codex.exe"):
                try:
                    info = candidate.stat()
                    if stat.S_ISREG(info.st_mode):
                        found[candidate] = info.st_mtime_ns
                except OSError:
                    continue  # Updates may remove an older cached executable.
        except OSError:
            continue
    return sorted(found, key=lambda path: (found[path], str(path).casefold()), reverse=True)


def find_codex():
    found = shutil.which("codex")
    candidates = ([Path(found)] if found else []) + [Path.home() / ".local/bin/codex"]
    if sys.platform == "win32":
        candidates += windows_codex_candidates()
    else:
        candidates += [Path("/opt/homebrew/bin/codex"), Path("/usr/local/bin/codex")]
        candidates += sorted((Path.home() / ".nvm/versions/node").glob("*/bin/codex"), reverse=True)
    for candidate in candidates:
        if candidate.is_file():
            if candidate.suffix.lower() in (".cmd", ".bat"):
                script = candidate.parent / "node_modules/@openai/codex/bin/codex.js"
                node = shutil.which("node")
                if node and script.is_file():
                    return [node, str(script)]
                continue  # Never pass prompts through cmd.exe or shell=True.
            return [str(candidate)]
    raise UserError("未找到 Codex CLI。请先安装官方 Codex CLI，并用 ChatGPT 登录；桌面应用安装本身不保证命令行可用。")


def process_options(command):
    # Keep normal platform/auth locations, but don't inherit API keys, endpoint
    # overrides, other agent task ids, debugging or plugin configuration.
    names = ("HOME", "USER", "LOGNAME", "PATH", "TMPDIR", "TEMP", "TMP", "LANG", "LC_ALL",
             "SystemRoot", "WINDIR", "USERPROFILE", "APPDATA", "LOCALAPPDATA", "CODEX_HOME")
    env = {name: os.environ[name] for name in names if name in os.environ}
    env["PATH"] = str(Path(command[0]).parent) + os.pathsep + env.get("PATH", "")
    options = {"env": env, "shell": False}
    if os.name == "nt":
        options["creationflags"] = subprocess.CREATE_NO_WINDOW
    return options


class CodexProbeError(UserError):
    """Only safe preflight metadata; never keep CLI output or conversation data."""
    def __init__(self, message, diagnostics):
        super().__init__(message)
        self.diagnostics = diagnostics


def write_probe_diagnostic(error, *, directory=None):
    """Keep the last failed UI preflight, without stdout/stderr, tokens or prompts."""
    if not isinstance(error, CodexProbeError):
        return
    if directory is None:
        if sys.platform == "win32":
            directory = Path.home() / "AppData/Local/ForeverAI/Diagnostics"
        elif sys.platform == "darwin":
            directory = Path.home() / "Library/Logs/ForeverAI"
        else:
            directory = Path.home() / ".local/state/forever-ai"
    temporary = None
    try:
        directory = Path(directory)
        directory.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=directory,
                                         prefix="codex-probe-", suffix=".tmp", delete=False) as stream:
            temporary = Path(stream.name)
            json.dump(error.diagnostics, stream, ensure_ascii=False, indent=2)
        temporary.replace(directory / "codex-probe.json")
    except OSError:
        pass  # Logging must not replace the useful connection error.
    finally:
        if temporary is not None:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass


def probe_codex(*, runner=None, command=None, diagnostics=None):
    report = diagnostics if diagnostics is not None else {}
    report.clear()
    report.update(schemaVersion=1, timestampUtc=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                  passed=False, phase="discovery", modelRequestSent=False)
    run = runner or subprocess.run
    def fail(code, message):
        report["failureCode"] = code
        location = "\nCLI：" + " | ".join(command) if command else ""
        raise CodexProbeError(message + location, dict(report))
    try:
        command = command or find_codex()
        report["command"] = list(command)
        report["phase"] = "help"
        with tempfile.TemporaryDirectory(prefix="forever-cli-check-") as cwd:
            help_result = run([*command, "exec", "--help"], capture_output=True, timeout=10,
                              cwd=cwd, **process_options(command))
            report.update(returncode=help_result.returncode, stdoutBytes=len(help_result.stdout),
                          stderrBytes=len(help_result.stderr))
            if help_result.returncode:
                fail("help_process_failed", f"Codex CLI 启动检查失败（退出码 {help_result.returncode}），"
                     "尚未验证版本支持；没有发送模型请求。")
            help_text = (help_result.stdout + help_result.stderr).decode("utf-8", errors="replace")
            missing = [flag for flag in REQUIRED_FLAGS if flag not in help_text]
            report["missingFlags"] = missing
            if not help_text.strip():
                fail("empty_help", "Codex CLI 未返回帮助内容，无法检查隔离能力；没有发送模型请求。")
            if missing:
                fail("unsupported_flags", "当前 Codex CLI 版本未提供所需参数：" + ", ".join(missing)
                     + "。请更新这份官方 CLI 后重试；没有发送模型请求。")
            report["phase"] = "login_status"
            for key in ("returncode", "stdoutBytes", "stderrBytes"):
                report.pop(key, None)
            result = run([*command, "login", "status"], capture_output=True, timeout=10,
                         cwd=cwd, **process_options(command))
            report.update(returncode=result.returncode, stdoutBytes=len(result.stdout),
                          stderrBytes=len(result.stderr))
            status = (result.stdout + result.stderr).decode("utf-8", errors="replace")
            if result.returncode and "not logged in" not in status.lower():
                fail("login_check_failed", f"Codex CLI 登录状态检查失败（退出码 {result.returncode}）；"
                     "没有发送模型请求。")
            if result.returncode or "logged in using chatgpt" not in status.lower():
                fail("chatgpt_login_required", "Codex CLI 尚未通过 ChatGPT 登录。请在 Codex 官方登录流程中登录后重试。")
    except CodexProbeError:
        raise
    except subprocess.TimeoutExpired:
        fail("timeout", "Codex CLI 检查超时；没有发送模型请求。")
    except OSError as exc:
        report.update(osError=exc.errno, windowsError=getattr(exc, "winerror", None))
        fail("os_error", "无法运行 Codex CLI 检查；没有发送模型请求。")
    except UserError:
        fail("not_found", "未找到 Codex CLI。请先安装官方 Codex CLI，并用 ChatGPT 登录。")
    report.update(passed=True, phase="complete")
    return "已连接本机 Codex · ChatGPT 登录 · 使用现有账号额度"


def codex_command(command, model, *, search):
    if model != AUTO_MODEL and not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,149}", model):
        raise UserError("Codex 模型 ID 无效。")
    args = [*command, "exec", "--ignore-user-config", "--ephemeral", "--skip-git-repo-check",
            "--sandbox", "read-only", "--json", "--color", "never"]
    if model != AUTO_MODEL:
        args += ["--model", model]
    for feature in DISABLED_FEATURES:
        args += ["--disable", feature]
    # Current Codex models may route even web tools through the isolated JS host.
    # Disabling that runtime breaks search; it does not grant shell/game tools.
    args += ["--enable", "skip_host_skill_discovery", "--enable", "code_mode_host"]
    args += ["--enable", "image_generation"]
    for setting in ('approval_policy="never"', 'forced_login_method="chatgpt"', 'project_doc_max_bytes=0',
                    'mcp_servers={}', 'model_reasoning_effort="low"', 'history.persistence="none"',
                    'web_search="live"' if search else 'web_search="disabled"'):
        args += ["-c", setting]
    return args


def generated_artifacts(artifact_root, thread_id, request_started):
    """Read new PNGs only in the exact thread directory emitted by this CLI call.

    Current exec JSONL omits image events; the official image extension saves at
    CODEX_HOME/generated_images/<thread-id>. No model-specified path, auth file,
    history scan or other thread is consulted. CLI-owned originals are preserved.
    """
    if not re.fullmatch(r"[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}", thread_id or ""):
        return []
    root = Path(artifact_root) / "generated_images"
    directory = root / thread_id
    pictures = []
    try:
        if linked_path(root) or linked_path(directory) or linked_windows_ancestor(directory) or not directory.is_dir():
            return []
        with os.scandir(directory) as entries:
            for index, entry in enumerate(entries):
                if index >= 12 or len(pictures) >= 3:
                    break
                if not re.fullmatch(r"[A-Za-z0-9_-]+\.png", entry.name) or not entry.is_file(follow_symlinks=False):
                    continue
                if linked_path(entry.path):
                    continue
                with artifact_stream(entry.path) as stream:
                    info = os.fstat(stream.fileno())
                    if (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_mtime < request_started
                            or info.st_size > 8_000_000):
                        continue
                    contents = stream.read(8_000_001)
                if len(contents) <= 8_000_000:
                    pictures.append(ReplyImage(normalize_image(contents), "AI 示意图", generated=True))
    except (OSError, UserError):
        pass  # Keep the ordinary reply; never broaden access to locate an image.
    return pictures


def parse_codex_output(raw, *, directory=None, artifact_root=None, request_started=None):
    if len(raw) > 32_000_000:
        raise UserError("Codex 返回内容过大。")
    texts, pictures = [], []
    complete = False
    thread_id = None
    for line in raw.splitlines():
        try:
            event = json.loads(line)
        except (ValueError, TypeError):
            continue
        if event.get("type") in ("turn.failed", "error"):
            raise UserError("Codex 请求未完成，请检查登录、模型可用性或账号额度；未自动切换到付费 API。")
        if event.get("type") == "thread.started" and thread_id is None:
            thread_id = event.get("thread_id")
        if event.get("type") == "turn.completed":
            complete = True
        if event.get("type") != "item.completed":
            continue
        item = event.get("item", {})
        if item.get("type") == "agent_message":
            texts.append(str(item.get("text", "")))
        elif item.get("type") in ("image_generation", "imageGeneration") and len(pictures) < 3:
            encoded = item.get("result", "")
            if encoded.startswith("data:image/"):
                encoded = encoded.partition(",")[2]
            if encoded:
                try:
                    pictures.append(ReplyImage(decode_image(encoded), "AI 示意图", generated=True))
                except UserError:
                    pass
    text, urls = extract_images("\n\n".join(texts))
    # Some CLI versions return generated images as workspace Markdown paths.
    # Only inspect image files inside this request's private temporary directory.
    if directory and not pictures:
        root = Path(directory).resolve()
        for match in re.finditer(r"!\[([^\]\n]*)\]\(([^\s)]+)\)", text):
            path = Path(match[2])
            if not path.is_absolute():
                path = root / path
            path = path.resolve()
            if root in path.parents and path.suffix.lower() in (".png", ".jpg", ".jpeg", ".webp") and path.is_file():
                if path.stat().st_size <= 8_000_000 and len(pictures) < 3:
                    pictures.append(ReplyImage(normalize_image(path.read_bytes()), "AI 示意图", generated=True))
                    text = text.replace(match[0], "")
    if complete and not pictures and artifact_root is not None and request_started is not None:
        pictures = generated_artifacts(artifact_root, thread_id, request_started)
    if not complete or not (text.strip() or pictures or urls):
        raise UserError("Codex 未返回完整回答；没有自动重试。")
    return Answer(text.strip(), images=(pictures + urls)[:3])


def ask_codex(model, prompt, *, snapshot=None, screenshot=None, history=(), search=True,
              runner=None, command=None):
    diagnostics = {}
    probe_codex(runner=runner, command=command, diagnostics=diagnostics)
    command = diagnostics["command"]  # Use precisely the executable we checked.
    _, context = build_request("OpenAI", "codex-default" if model == AUTO_MODEL else model, prompt,
                               snapshot=snapshot, screenshot=screenshot, history=history, search=search)
    # A real image is attached separately. Don't also copy base64 into the text prompt.
    messages = context["input"]
    messages[-1]["content"] = messages[-1]["content"][:1]
    instruction = SYSTEM + "\nOnly answer the user's WoW question. Do not inspect files or run commands."
    instruction += ("\nChoose text, sourced images, or the image-generation tool according to the user's request. "
                    "Use image generation only when the user wants a new illustration; at most one per turn. "
                    "Label generated images AI 示意图; never invent a factual game map. "
                    "If a needed tool is unavailable, explain that honestly; never claim you generated an image without a result.")
    payload = (instruction + "\nConversation data:\n" + json.dumps(messages, ensure_ascii=False)).encode("utf-8")
    try:
        with tempfile.TemporaryDirectory(prefix="forever-codex-") as cwd:
            args = codex_command(command, model, search=search)
            if screenshot:
                path = Path(cwd) / "selected-window.png"
                path.write_bytes(screenshot.png)
                path.chmod(0o600)
                args += ["--image", str(path)]
            options = process_options(command)
            started = time.time()
            result = (runner or subprocess.run)([*args, "-"], input=payload, capture_output=True,
                                                timeout=240, cwd=cwd, **options)
            if result.returncode:
                raise UserError("Codex 调用失败，请检查账号额度、CLI 版本或所选模型。没有读取登录令牌或自动切换 API。")
            artifact_root = Path(options["env"].get("CODEX_HOME", str(Path.home() / ".codex")))
            return parse_codex_output(result.stdout, directory=cwd,
                                      artifact_root=artifact_root if artifact_root.is_absolute() else None,
                                      request_started=started)
    except subprocess.TimeoutExpired:
        raise UserError("Codex 调用超时；请求可能已使用额度，没有自动重试。") from None
    except OSError:
        raise UserError("无法启动 Codex CLI，请检查安装。") from None
