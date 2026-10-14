"""Build a Windows GUI executable from an exact source commit, without installation."""
import argparse
import hashlib
import importlib.metadata
import io
import json
from pathlib import Path, PurePosixPath
import platform
import re
import shutil
import subprocess
import sys
import tempfile
import tomllib
import zipfile


def export_source(root, commit, destination):
    archive = subprocess.check_output(["git", "archive", "--format=zip", commit], cwd=root)
    with zipfile.ZipFile(io.BytesIO(archive)) as zipped:
        for item in zipped.infolist():
            name = PurePosixPath(item.filename)
            if name.is_absolute() or ".." in name.parts or (item.external_attr >> 16) & 0o170000 == 0o120000:
                raise RuntimeError("Unsafe archive member")
            target = destination.joinpath(*name.parts)
            if item.is_dir():
                target.mkdir(parents=True, exist_ok=True)
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(zipped.read(item))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--commit", required=True)
    args = parser.parse_args()
    if sys.platform != "win32" or platform.machine().lower() not in ("amd64", "x86_64"):
        raise SystemExit("Build using Windows x64 CPython")
    if not re.fullmatch(r"[0-9a-f]{40}", args.commit):
        raise SystemExit("Pass a full fixed commit SHA")
    root = Path(__file__).resolve().parents[1]
    actual = subprocess.check_output(["git", "rev-parse", args.commit + "^{commit}"], cwd=root, text=True).strip()
    if actual != args.commit:
        raise SystemExit("Commit mismatch")
    output = root / "dist" / ("windows-" + actual[:12])
    if output.exists():
        raise SystemExit("Output already exists; preserve it and build a new commit")
    runtime = root / ".runtime"
    runtime.mkdir(exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix="windows-build-", dir=runtime))
    source = work / "source"
    source.mkdir()
    export_source(root, actual, source)
    for requirement in (source / "requirements-windows-build.txt").read_text(encoding="utf-8").splitlines():
        if requirement and not requirement.startswith("#"):
            name, wanted = requirement.split("==")
            if importlib.metadata.version(name) != wanted:
                raise SystemExit("Install the fixed Windows build requirements: " + name)
    version = tomllib.loads((source / "pyproject.toml").read_text(encoding="utf-8"))["project"]["version"]
    checks = [("contracts", [sys.executable, "-X", "utf8", str(source / "scripts/check.py")]),
              ("hidden-gui", [sys.executable, "-X", "utf8", str(source / "scripts/gui_smoke.py")])]
    for name, command in checks:
        result = subprocess.run(command, cwd=source, capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW)
        (work / (name + ".log")).write_bytes(result.stdout + result.stderr)
        if result.returncode:
            raise SystemExit("Fixed source check failed; see " + str(work / (name + ".log")))
    native_helper = work / "native" / "forever-capture-windows.exe"
    result = subprocess.run([sys.executable, "-X", "utf8", str(source / "scripts/build_windows_capture.py"),
                             "--output", str(native_helper)], cwd=source, capture_output=True,
                            creationflags=subprocess.CREATE_NO_WINDOW)
    (work / "windows-capture-build.log").write_bytes(result.stdout + result.stderr)
    if result.returncode or not native_helper.is_file():
        raise SystemExit("Windows capture build failed; see " + str(work / "windows-capture-build.log"))
    result = subprocess.run([str(native_helper), "--self-test"], cwd=work, capture_output=True,
                            timeout=10, creationflags=subprocess.CREATE_NO_WINDOW)
    (work / "windows-capture-self-test.log").write_bytes(result.stdout + result.stderr)
    native_evidence = json.loads(result.stdout) if result.returncode == 0 else {}
    if not native_evidence.get("passed") or native_evidence.get("captureStarted") is not False:
        raise SystemExit("Windows capture synthetic self-test failed; see " + str(work / "windows-capture-self-test.log"))
    from PIL import Image, ImageDraw
    icon = Image.new("RGBA", (256, 256), "#111b23")
    draw = ImageDraw.Draw(icon)
    draw.rounded_rectangle((16, 16, 240, 240), radius=44, outline="#dfc48c", width=10)
    draw.line([(78, 202), (78, 58), (187, 58)], fill="#dfc48c", width=23)
    draw.line([(78, 120), (161, 120)], fill="#dfc48c", width=21)
    icon_path = work / "forever.ico"
    icon.save(icon_path, sizes=[(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    import os
    env = dict(os.environ, PYINSTALLER_CONFIG_DIR=str(work / "pyinstaller-cache"), PYTHONUTF8="1")
    command = [sys.executable, "-m", "PyInstaller", "--onedir", "--windowed", "--noupx", "--name", "Forever AI",
               "--icon", str(icon_path), "--manifest", str(source / "native/windows.manifest"),
               "--distpath", str(output), "--workpath", str(work / "build"), "--specpath", str(work),
               "--paths", str(source), "--exclude-module", "lupa", "--exclude-module", "unittest",
               "--add-binary", str(native_helper) + os.pathsep + "native",
               str(source / "scripts/windows_entry.py")]
    result = subprocess.run(command, cwd=source, env=env, capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW)
    (work / "pyinstaller.log").write_bytes(result.stdout + result.stderr)
    if result.returncode:
        raise SystemExit("Windows packaging failed; see " + str(work / "pyinstaller.log"))
    app = output / "Forever AI"
    executable = app / "Forever AI.exe"
    check_report = work / "bundle-check.json"
    result = subprocess.run([str(executable), "--self-test-report", str(check_report)], cwd=app,
                            timeout=30, creationflags=subprocess.CREATE_NO_WINDOW)
    evidence = json.loads(check_report.read_text(encoding="utf-8")) if check_report.exists() else {}
    if result.returncode or not evidence.get("passed"):
        raise SystemExit("Built executable failed its offline check; see " + str(check_report))
    shutil.copytree(source / "addon/ForeverAI", app / "addon/ForeverAI")
    shutil.copyfile(source / "docs/windows.md", app / "Windows-guide.md")
    provenance = {"sourceCommit": actual, "version": version, "platform": "Windows", "architecture": "x64",
                  "signature": "unsigned local build", "hiddenBundleCheck": evidence,
                  "captureBackend": "Windows.Graphics.Capture (selected HWND)",
                  "captureHelperSha256": hashlib.sha256(native_helper.read_bytes()).hexdigest(),
                  "captureHelperSyntheticCheck": native_evidence,
                  "gameClientTested": False, "realCaptureTested": False, "liveApiTested": False}
    (app / "source.json").write_text(json.dumps(provenance, ensure_ascii=False, indent=2), encoding="utf-8")
    archive = output / ("ForeverAI-Windows-x64-" + actual[:12] + ".zip")
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as zipped:
        for item in sorted(app.rglob("*")):
            if item.is_file():
                zipped.write(item, item.relative_to(output))
    manifest = dict(provenance, app=str(executable), archive=archive.name,
                    sha256=hashlib.sha256(archive.read_bytes()).hexdigest(),
                    executableSha256=hashlib.sha256(executable.read_bytes()).hexdigest(),
                    buildLogs=str(work))
    (output / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(manifest, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
