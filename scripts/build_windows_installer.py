"""Wrap an exact, checked Windows bundle in a current-user Inno Setup installer."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import zipfile


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def checked_bundle(output, commit):
    """Require the pristine folder and archive produced by build_windows.py."""
    manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
    app = output / "Forever AI"
    provenance = json.loads((app / "source.json").read_text(encoding="utf-8"))
    for evidence in (manifest, provenance):
        if evidence.get("sourceCommit") != commit or not evidence.get("hiddenBundleCheck", {}).get("passed"):
            raise RuntimeError("Bundle source or packaged self-test evidence mismatch")
        if not evidence.get("captureHelperSyntheticCheck", {}).get("passed"):
            raise RuntimeError("Missing native capture synthetic self-test")
    version = manifest["version"]
    if not re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", version) or provenance.get("version") != version:
        raise RuntimeError("Invalid or inconsistent bundle version")
    archive_name = manifest["archive"]
    if Path(archive_name).name != archive_name:
        raise RuntimeError("Archive must be inside the fixed output directory")
    archive = output / archive_name
    if sha256(archive) != manifest.get("sha256"):
        raise RuntimeError("Bundle archive hash mismatch")
    actual_files = {}
    for path in app.rglob("*"):
        if path.is_symlink() or getattr(path.lstat(), "st_file_attributes", 0) & 0x400:
            raise RuntimeError("Bundle must not contain links")
        if path.is_file():
            actual_files[path.relative_to(output).as_posix()] = path
    with zipfile.ZipFile(archive) as zipped:
        entries = [item for item in zipped.infolist() if not item.is_dir()]
        if len(entries) != len(actual_files) or {item.filename for item in entries} != set(actual_files):
            raise RuntimeError("Bundle folder differs from the checked archive")
        for item in entries:
            if actual_files[item.filename].read_bytes() != zipped.read(item):
                raise RuntimeError("Bundle file differs from the checked archive: " + item.filename)
    expected_addon = {"ForeverAI.toc", "ForeverAI.lua", "Snapshot.lua"}
    if {item.name for item in (app / "addon/ForeverAI").iterdir()} != expected_addon:
        raise RuntimeError("Installer AddOn file list needs updating")
    return app, version


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--commit", required=True)
    parser.add_argument("--iscc", required=True, type=Path, help="Inno Setup 6.5+ ISCC.exe")
    parser.add_argument("--test", action="store_true", help="Run isolated silent installer tests (CI only)")
    args = parser.parse_args()
    if sys.platform != "win32":
        raise SystemExit("Build the installer on Windows")
    if not re.fullmatch(r"[0-9a-f]{40}", args.commit):
        raise SystemExit("Pass a full fixed commit SHA")
    root = Path(__file__).resolve().parents[1]
    actual = subprocess.check_output(["git", "rev-parse", args.commit + "^{commit}"], cwd=root, text=True).strip()
    if actual != args.commit:
        raise SystemExit("Commit mismatch")
    if not args.iscc.is_file():
        raise SystemExit("Inno Setup compiler not found")
    output = root / "dist" / ("windows-" + actual[:12])
    app, version = checked_bundle(output, actual)
    executable = output / "ForeverAI-Setup-x64.exe"
    if executable.exists():
        raise SystemExit("Installer output exists; preserve it and build a new commit")
    runtime = root / ".runtime"
    runtime.mkdir(exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix="installer-build-", dir=runtime))
    script = work / "ForeverAI.iss"
    source_script = subprocess.check_output(["git", "show", actual + ":installer/ForeverAI.iss"], cwd=root)
    script.write_text(source_script.decode("utf-8-sig"), encoding="utf-8-sig")
    language = work / "ChineseSimplified.isl"
    language.write_bytes(subprocess.check_output(
        ["git", "show", actual + ":installer/languages/ChineseSimplified.isl"], cwd=root))
    result = subprocess.run([str(args.iscc.resolve()), "/Qp", "/DBundleDir=" + str(app),
                             "/DAppVersion=" + version, "/DOutputDir=" + str(output),
                             "/DChineseMessagesFile=" + str(language), str(script)],
                            cwd=root, capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW)
    (work / "compiler.log").write_bytes(result.stdout + result.stderr)
    if result.returncode or not executable.is_file():
        raise SystemExit("Installer compile failed; see " + str(work / "compiler.log"))
    manifest = {"sourceCommit": actual, "version": version, "installer": executable.name,
                "sha256": sha256(executable), "platform": "Windows", "architecture": "x64",
                "selfContained": True, "signature": "unsigned", "syntheticInstallPassed": False,
                "gameClientTested": False, "realCaptureTested": False, "liveApiTested": False}
    if args.test:
        checker = work / "check_windows_installer.py"
        checker.write_bytes(subprocess.check_output(["git", "show", actual + ":scripts/check_windows_installer.py"], cwd=root))
        report = work / "synthetic-install.json"
        result = subprocess.run([sys.executable, "-X", "utf8", str(checker), "--installer", str(executable),
                                 "--bundle", str(app), "--report", str(report)], cwd=root,
                                capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW)
        (work / "synthetic-install.log").write_bytes(result.stdout + result.stderr)
        evidence = json.loads(report.read_text(encoding="utf-8")) if report.exists() else {}
        if result.returncode or not evidence.get("passed"):
            raise SystemExit("Synthetic installer check failed; see " + str(work / "synthetic-install.log"))
        manifest["syntheticInstallPassed"] = True
        manifest["syntheticChecks"] = evidence["checks"]
    (output / "installer-manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
