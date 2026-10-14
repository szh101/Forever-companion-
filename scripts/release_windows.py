"""Verify fixed-source Windows assets and publish them from GitHub Actions.

Only explicitly named public files are uploaded. Local build manifests, logs,
authentication data and runtime directories never become release assets.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import tomllib
import urllib.error
import urllib.parse
import urllib.request
import zipfile


ROOT = Path(__file__).resolve().parents[1]


def digest(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def git(root: Path, *args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=root, text=True, encoding="utf-8").strip()


def prepare(root: Path, commit: str) -> dict:
    if not re.fullmatch(r"[0-9a-f]{40}", commit) or git(root, "rev-parse", "HEAD") != commit:
        raise ValueError("Release requires the exact checked-out commit")
    if git(root, "status", "--porcelain", "--untracked-files=no"):
        raise ValueError("Tracked source files changed after checkout")
    marker = json.loads((root / "release/windows.json").read_text(encoding="utf-8"))
    version = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))["project"]["version"]
    if not re.fullmatch(r"\d+\.\d+\.\d+", version) or marker.get("version") != version:
        raise ValueError("Release marker must match the application version")
    revision = marker.get("revision")
    if type(revision) is not int or not 1 <= revision <= 9999:
        raise ValueError("Release revision must be a positive integer")
    output = root / "dist" / ("windows-" + commit[:12])
    bundle = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
    installer = json.loads((output / "installer-manifest.json").read_text(encoding="utf-8"))
    for manifest in (bundle, installer):
        if manifest.get("sourceCommit") != commit or manifest.get("version") != version:
            raise ValueError("Build evidence does not match this release")
    if (bundle.get("architecture") != "x64" or bundle.get("platform") != "Windows"
            or bundle.get("hiddenBundleCheck", {}).get("passed") is not True
            or bundle.get("captureHelperSyntheticCheck", {}).get("passed") is not True
            or bundle.get("captureHelperSyntheticCheck", {}).get("captureStarted") is not False):
        raise ValueError("Packaged application checks have not passed")
    if installer.get("syntheticInstallPassed") is not True or installer.get("selfContained") is not True:
        raise ValueError("Self-contained installer has not passed its synthetic installation check")
    installer_name = "ForeverAI-Setup-x64.exe"
    portable_name = "ForeverAI-Windows-x64-" + commit[:12] + ".zip"
    assets = [output / installer_name, output / portable_name]
    for manifest, name, key in ((installer, installer_name, "installer"), (bundle, portable_name, "archive")):
        path = output / name
        if manifest.get(key) != name or path.is_symlink() or not path.is_file() or digest(path) != manifest.get("sha256"):
            raise ValueError("Public asset name or checksum does not match build evidence")
    addon_files = ("ForeverAI.toc", "ForeverAI.lua", "Snapshot.lua")
    addon_data = {name: subprocess.check_output(
        ["git", "show", commit + ":addon/ForeverAI/" + name], cwd=root) for name in addon_files}
    toc_version = re.search(r"^## Version: (\d+\.\d+\.\d+)\s*$",
                            addon_data["ForeverAI.toc"].decode("utf-8"), re.MULTILINE)
    if toc_version is None:
        raise ValueError("The committed AddOn has no valid version")
    addon = output / ("ForeverAI-AddOn-" + toc_version.group(1) + ".zip")
    with zipfile.ZipFile(addon, "w", zipfile.ZIP_DEFLATED) as archive:
        for name in addon_files:
            item = zipfile.ZipInfo("ForeverAI/" + name, date_time=(2020, 1, 1, 0, 0, 0))
            item.compress_type = zipfile.ZIP_DEFLATED
            item.external_attr = 0o100644 << 16
            archive.writestr(item, addon_data[name])
    assets.append(addon)
    checksums = output / "SHA256SUMS.txt"
    checksums.write_text("".join(digest(path) + "  " + path.name + "\n" for path in assets), encoding="ascii")
    assets.append(checksums)
    notes = (
        "## Windows installation\n\n"
        "Download **ForeverAI-Setup-x64.exe** and run it. Python is included. "
        "The installer installs the desktop Companion and can also install the AddOn "
        "after you select your actual Forever game client folder. "
        "It does not install or sign in to an AI service.\n\n"
        "下载 **ForeverAI-Setup-x64.exe** 并运行，无需安装 Python。"
        "安装向导安装桌面 Companion；选择实际使用的 Forever 游戏客户端目录后，"
        "也可同时安装 AddOn。AI 账号或 API Key 仍需由你自己配置。\n\n"
        "- Setup is an unsigned Windows x64 installer. Windows may display an unknown-publisher warning.\n"
        "- The portable ZIP is optional; keep its entire application folder together.\n"
        "- The AddOn ZIP is for manual AddOn-only installation.\n"
        "- `SHA256SUMS.txt` contains checksums for these three downloads.\n"
        "- Automated checks cover Python/Lua contracts, the macOS native build, "
        "hidden Windows UI, the bundled application, and installation into a synthetic client. "
        "They do not establish in-game behavior, live capture, live AI access, or Blizzard approval.\n"
        "- This release does not include a macOS application package.\n\n"
        "Source commit: `" + commit + "`\n"
    )
    return {"tag": f"v{version}-windows.{revision}", "commit": commit,
            "name": f"Forever AI {version} — Windows installer {revision}",
            "body": notes, "assets": assets}


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, file, code, message, headers, newurl):
        raise ValueError("Refusing to redirect a release upload with authorization")


def request_json(url: str, token: str, *, method: str = "GET", payload=None, asset: Path | None = None):
    parsed = urllib.parse.urlsplit(url)
    if parsed.scheme != "https" or parsed.hostname not in ("api.github.com", "uploads.github.com") or parsed.username or parsed.password or parsed.port:
        raise ValueError("Unexpected GitHub release API target")
    headers = {"Accept": "application/vnd.github+json", "Authorization": "Bearer " + token,
               "X-GitHub-Api-Version": "2022-11-28", "User-Agent": "ForeverAI-release"}
    data = None
    if asset is not None:
        data = asset.read_bytes()
        headers["Content-Type"] = "application/octet-stream"
    elif payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        with urllib.request.build_opener(NoRedirect()).open(request, timeout=180) as response:
            body = response.read(4 * 1024 * 1024)
            return json.loads(body) if body else None
    except urllib.error.HTTPError as error:
        if method == "GET" and error.code == 404:
            return None
        raise RuntimeError(f"GitHub release API returned HTTP {error.code}") from None


def verify_tag_target(base: str, tag: str, commit: str, token: str, *, allow_missing: bool) -> None:
    reference = request_json(base + "/git/ref/tags/" + urllib.parse.quote(tag, safe=""), token)
    if reference is None:
        if allow_missing:
            return
        raise RuntimeError("Published release tag was not found")
    target = reference.get("object", {})
    seen = set()
    for _ in range(8):
        sha = target.get("sha", "")
        if not re.fullmatch(r"[0-9a-f]{40}", sha) or sha in seen:
            raise ValueError("Release tag has an invalid target")
        seen.add(sha)
        if target.get("type") == "commit":
            if sha != commit:
                raise ValueError("Release tag points at a different source commit; leave it unchanged")
            return
        if target.get("type") != "tag":
            raise ValueError("Release tag does not resolve to a commit")
        annotated = request_json(base + "/git/tags/" + sha, token)
        target = annotated.get("object", {}) if annotated else {}
    raise ValueError("Release tag nesting is too deep")


def publish(release: dict) -> str:
    repository = os.environ.get("GITHUB_REPOSITORY", "")
    if (os.environ.get("GITHUB_ACTIONS") != "true" or os.environ.get("GITHUB_REF") != "refs/heads/main"
            or os.environ.get("GITHUB_SHA") != release["commit"]
            or not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository)):
        raise ValueError("Publishing is restricted to the exact main commit in GitHub Actions")
    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        raise ValueError("GitHub Actions release token is unavailable")
    base = "https://api.github.com/repos/" + repository
    verify_tag_target(base, release["tag"], release["commit"], token, allow_missing=True)
    tag_url = base + "/releases/tags/" + urllib.parse.quote(release["tag"], safe="")
    existing = request_json(tag_url, token)
    if existing is None:
        # A tag lookup may omit an unpublished draft. Resume only our exact
        # draft after a failed upload; never create duplicate release records.
        drafts = request_json(base + "/releases?per_page=100", token) or []
        matches = [item for item in drafts if item.get("tag_name") == release["tag"]]
        if len(matches) > 1:
            raise ValueError("More than one draft uses this release tag; leave them unchanged")
        existing = matches[0] if matches else None
    if existing is not None:
        if not existing.get("draft"):
            raise ValueError("This release is already published; increment release/windows.json revision")
        if existing.get("target_commitish") != release["commit"] or existing.get("body") != release["body"]:
            raise ValueError("Existing draft belongs to a different build; leave it unchanged")
        result = existing
    else:
        result = request_json(base + "/releases", token, method="POST", payload={
            "tag_name": release["tag"], "target_commitish": release["commit"], "name": release["name"],
            "body": release["body"], "draft": True, "prerelease": False})
    release_id = result["id"]
    assets_url = base + f"/releases/{release_id}/assets"
    current_assets = request_json(assets_url, token) or []
    expected_names = {path.name for path in release["assets"]}
    if any(item["name"] not in expected_names for item in current_assets):
        raise ValueError("Draft contains unexpected assets; leave it unpublished")
    for item in current_assets:
        request_json(base + f"/releases/assets/{item['id']}", token, method="DELETE")
    for path in release["assets"]:
        url = "https://uploads.github.com/repos/" + repository + f"/releases/{release_id}/assets?"
        uploaded = request_json(url + urllib.parse.urlencode({"name": path.name}), token, method="POST", asset=path)
        if uploaded.get("state") != "uploaded" or uploaded.get("size") != path.stat().st_size:
            raise RuntimeError("Release asset upload did not complete")
        remote_digest = uploaded.get("digest")
        if remote_digest is not None and remote_digest != "sha256:" + digest(path):
            raise RuntimeError("GitHub asset digest differs from the local file")
    final_assets = request_json(assets_url, token) or []
    if {item["name"] for item in final_assets} != expected_names or len(final_assets) != len(expected_names):
        raise RuntimeError("The draft release does not contain exactly the required downloads")
    verify_tag_target(base, release["tag"], release["commit"], token, allow_missing=True)
    result = request_json(base + f"/releases/{release_id}", token, method="PATCH",
                          payload={"draft": False, "make_latest": "true"})
    if result.get("draft") is not False:
        raise RuntimeError("Release publication was not confirmed")
    verify_tag_target(base, release["tag"], release["commit"], token, allow_missing=False)
    return result["html_url"]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--commit", required=True)
    parser.add_argument("--publish", action="store_true")
    args = parser.parse_args()
    release = prepare(ROOT, args.commit)
    print(json.dumps({"tag": release["tag"], "sourceCommit": release["commit"],
                      "assets": [path.name for path in release["assets"]]}, indent=2))
    if args.publish:
        print("Published: " + publish(release))


if __name__ == "__main__":
    main()
