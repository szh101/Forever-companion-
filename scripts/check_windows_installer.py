"""CI-only silent installation checks using synthetic directories, never a game."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--installer", required=True, type=Path)
    parser.add_argument("--bundle", required=True, type=Path)
    parser.add_argument("--report", required=True, type=Path)
    args = parser.parse_args()
    if sys.platform != "win32" or os.environ.get("CI", "").lower() != "true":
        raise SystemExit("Run this installer check on an isolated Windows CI runner (CI=true)")
    work = Path(tempfile.mkdtemp(prefix="forever-installer-check-"))
    client = work / "synthetic client 中文"
    addons = client / "Interface/AddOns"
    addons.mkdir(parents=True)
    (client / "Wow.exe").write_bytes(b"Synthetic marker; never executable or launched.")
    unrelated = addons / "OtherAddon/keep.txt"
    unrelated.parent.mkdir()
    unrelated.write_bytes(b"unrelated addon")
    destination = work / "companion application"
    checks = []

    def install(name, game=client, addon=True, success=True, lang="en"):
        command = [str(args.installer.resolve()), "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART",
                   "/SP-", "/NOICONS", "/TASKS=", "/LANG=" + lang, "/DIR=" + str(destination),
                   "/INSTALLADDON=" + ("yes" if addon else "no"), "/GAMECLIENT=" + str(game),
                   "/LOG=" + str(work / (name + ".log"))]
        result = subprocess.run(command, capture_output=True, timeout=180,
                                creationflags=subprocess.CREATE_NO_WINDOW)
        if (result.returncode == 0) != success:
            raise AssertionError(f"{name}: unexpected exit {result.returncode}; logs: {work}")
        checks.append(name)

    def verify_addon():
        for name in ("ForeverAI.toc", "ForeverAI.lua", "Snapshot.lua"):
            assert (addons / "ForeverAI" / name).read_bytes() == (args.bundle / "addon/ForeverAI" / name).read_bytes()
        assert unrelated.read_bytes() == b"unrelated addon"

    install("reject-invalid-client", game=work / "absent", success=False)
    assert not destination.exists()
    missing_exe = work / "not-a-client"
    (missing_exe / "Interface").mkdir(parents=True)
    install("reject-missing-game-executable", game=missing_exe, success=False)
    assert not destination.exists()
    install("fresh-install")
    verify_addon()
    for original in args.bundle.rglob("*"):
        if original.is_file():
            assert (destination / original.relative_to(args.bundle)).read_bytes() == original.read_bytes()
    checks.append("exact-bundle-installed")
    previous = addons / "ForeverAI/custom-note.txt"
    previous.write_bytes(b"original local note")
    (addons / "ForeverAI/ForeverAI.lua").write_bytes(b"previous addon")
    install("update-preserves-backup", lang="zhCN")
    verify_addon()
    backups = list((client / "Interface/ForeverAI-backups").glob("ForeverAI-*"))
    assert len(backups) == 1
    assert (backups[0] / "custom-note.txt").read_bytes() == b"original local note"
    assert (backups[0] / "ForeverAI.lua").read_bytes() == b"previous addon"
    assert not previous.exists()
    install("skip-addon", game=work / "absent", addon=False)
    verify_addon()
    assert len(list((client / "Interface/ForeverAI-backups").iterdir())) == 1
    # Junctions are created only inside this new temporary fixture. No real client
    # lookup, registry game discovery, executable launch, capture or clipboard.
    linked = work / "linked-client"
    link_result = subprocess.run(["cmd.exe", "/d", "/c", "mklink", "/J", str(linked), str(client)],
                                 capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW)
    if link_result.returncode:
        raise AssertionError("CI could not create the synthetic junction")
    try:
        install("reject-linked-client", game=linked, success=False)
    finally:
        linked.rmdir()  # Remove only the junction itself, never its target.
    verify_addon()
    uninstaller = destination / "unins000.exe"
    result = subprocess.run([str(uninstaller), "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART",
                             "/LOG=" + str(work / "uninstall.log")], capture_output=True, timeout=180,
                            creationflags=subprocess.CREATE_NO_WINDOW)
    assert result.returncode == 0
    assert not (destination / "Forever AI.exe").exists()
    verify_addon()
    assert (backups[0] / "custom-note.txt").read_bytes() == b"original local note"
    checks.append("uninstall-preserves-addon-and-backup")
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps({"passed": True, "checks": checks, "syntheticGame": True,
                                       "applicationLaunched": False, "realGameAccessed": False}, indent=2) + "\n",
                           encoding="utf-8")
    print(json.dumps({"passed": True, "checks": checks}))


if __name__ == "__main__":
    main()
