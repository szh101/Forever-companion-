"""Inspect release payloads without starting the app or installer.

Requires the locked PyInstaller build environment. Build logs and the local
build manifest are deliberately outside the app payload and are not inspected
or eligible for release by this command. Never prints matched private values.
"""
from __future__ import annotations

import argparse
import io
import json
import marshal
import os
from pathlib import Path, PurePosixPath
import re
import stat
import sys
import types
import zipfile


MAX_ITEM = 256 * 1024 * 1024
MAX_TOTAL = 1024 * 1024 * 1024
EMAIL = re.compile(r"(?i)(?<![\w.+-])[\w.+-]+@[\w.-]+\.[a-z]{2,}(?![\w.-])")
SAFE_EMAIL_DOMAINS = {"example.com", "example.org", "example.net", "users.noreply.github.com"}
PRIVATE_COMPONENTS = {".git", ".runtime", ".venv"}


def linked(path: Path) -> bool:
    info = path.lstat()
    return bool(path.is_symlink() or getattr(info, "st_file_attributes", 0)
                & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400))


class Inspector:
    def __init__(self, prefixes, forbidden_text=()):
        self.patterns = []
        for prefix in prefixes:
            for variant in {str(prefix), str(prefix).replace("\\", "/"), str(prefix).replace("/", "\\")}:
                for encoding in ("utf-8", "utf-16le", "utf-16be"):
                    self.patterns.append(("build-workspace-or-home", variant.lower().encode(encoding)))
        for text in forbidden_text:
            if text:
                for encoding in ("utf-8", "utf-16le", "utf-16be"):
                    self.patterns.append(("explicit-forbidden-text", text.lower().encode(encoding)))
        self.findings = set()
        self.items = 0
        self.code_objects = 0
        self.decoded_bytes = 0
        self.archives = 0
        self.installer_scope = "not-provided"

    def issue(self, label, category):
        self.findings.add((label, category))

    def label(self, parent, name):
        name = str(name).replace("\\", "/")
        if (name.startswith("/") or re.match(r"^[a-zA-Z]:", name)
                or ".." in PurePosixPath(name).parts):
            self.issue(parent, "unsafe-archive-member")
            return parent + "!<unsafe-member>"
        # Archive member names can themselves contain a private string.
        raw = name.lower().encode("utf-8")
        if any(pattern in raw for _, pattern in self.patterns):
            self.issue(parent, "private-archive-member-name")
            return parent + "!<private-member>"
        return parent + "!" + name

    def inspect(self, label, data, first_party=False):
        self.items += 1
        self.decoded_bytes += len(data)
        if len(data) > MAX_ITEM or self.decoded_bytes > MAX_TOTAL:
            raise ValueError("Payload inspection limit exceeded")
        lowered = data.lower()
        for category, pattern in self.patterns:
            if pattern in lowered:
                self.issue(label, category)
        if first_party:
            for encoding in ("utf-8", "utf-16le"):
                decoded = data.decode(encoding, errors="ignore")
                for email in EMAIL.findall(decoded):
                    domain = email.rsplit("@", 1)[1].lower()
                    if domain not in SAFE_EMAIL_DOMAINS:
                        self.issue(label, "first-party-email")

    def code(self, label, value):
        if not isinstance(value, types.CodeType):
            return
        self.code_objects += 1
        filename = value.co_filename.replace("\\", "/")
        if filename.startswith("/") or re.match(r"^[a-zA-Z]:/", filename):
            self.issue(label, "absolute-code-filename")
        for child in value.co_consts:
            if isinstance(child, types.CodeType):
                self.code(label, child)

    def zip(self, label, stream, depth=0):
        if depth > 4:
            raise ValueError("Nested archive limit exceeded")
        self.archives += 1
        with zipfile.ZipFile(stream) as archive:
            for item in archive.infolist():
                name = self.label(label, item.filename)
                if item.is_dir():
                    continue
                if item.file_size > MAX_ITEM or self.decoded_bytes + item.file_size > MAX_TOTAL:
                    raise ValueError("Archive inspection limit exceeded")
                if stat.S_ISLNK(item.external_attr >> 16):
                    self.issue(name, "link-in-release-payload")
                    continue
                self.path_policy(name, item.filename)
                data = archive.read(item)
                first_party = self.first_party(name)
                self.inspect(name, data, first_party)
                if item.filename.endswith(".pyc"):
                    self.code(name, marshal.loads(data[16:]))
                if item.filename.lower().endswith(".zip"):
                    self.zip(name, io.BytesIO(data), depth + 1)

    @staticmethod
    def first_party(name):
        parts = str(name).replace("\\", "/").split("/")
        return ("_internal" not in parts and not name.lower().endswith((".exe", ".dll", ".pyd", ".zip", ".pyc")))

    def path_policy(self, label, name):
        parts = str(name).replace("\\", "/").split("/")
        if (PRIVATE_COMPONENTS.intersection(parts) or any(part == ".env" or part.startswith(".env.") for part in parts)
                or parts[-1].lower() in {"auth.json", "credentials.json", "manifest.json"}):
            self.issue(label, "private-or-local-only-file")

    def pyinstaller(self, path, label):
        from PyInstaller.archive.readers import CArchiveReader
        archive = CArchiveReader(str(path))
        self.archives += 1
        for name, entry in archive.toc.items():
            member = self.label(label, name)
            if entry[2] > MAX_ITEM or self.decoded_bytes + entry[2] > MAX_TOTAL:
                raise ValueError("Executable inspection limit exceeded")
            data = archive.extract(name)
            self.inspect(member, data)
            if entry[-1] in ("s", "m", "M"):
                code = marshal.loads(data)
                self.code(member, code)
                if name in {"windows_entry", "macos_entry"}:
                    self.inspect(member, data, first_party=True)
            if entry[-1] == "z":
                pyz = archive.open_embedded_archive(name)
                self.archives += 1
                for module in pyz.toc:
                    code = pyz.extract(module)
                    label_module = self.label(member, module)
                    if isinstance(code, types.CodeType):
                        self.inspect(label_module, marshal.dumps(code), module == "companion" or module.startswith("companion."))
                        self.code(label_module, code)

    def app(self, app):
        if not app.is_dir() or linked(app):
            raise ValueError("Expected a regular app directory")
        executable = app / "Forever AI.exe"
        if not executable.is_file() or linked(executable):
            raise ValueError("Missing regular app executable")
        for parent, directories, files in os.walk(app, followlinks=False):
            for name in list(directories):
                path = Path(parent) / name
                label = "app/" + path.relative_to(app).as_posix()
                self.path_policy(label, path.relative_to(app).as_posix())
                if linked(path):
                    self.issue(label, "link-in-release-payload")
                    directories.remove(name)
            for name in files:
                path = Path(parent) / name
                relative = path.relative_to(app).as_posix()
                label = "app/" + relative
                self.path_policy(label, relative)
                if linked(path):
                    self.issue(label, "link-in-release-payload")
                    continue
                if path.stat().st_size > MAX_ITEM:
                    raise ValueError("File inspection limit exceeded")
                self.inspect(label, path.read_bytes(), self.first_party(relative))
                if path.suffix.lower() == ".zip":
                    self.zip(label, path)
        self.pyinstaller(executable, "app/Forever AI.exe")

    def installer(self, installer):
        if not installer.is_file() or linked(installer) or installer.stat().st_size > MAX_ITEM:
            raise ValueError("Expected a regular bounded installer file")
        self.inspect("installer", installer.read_bytes())
        self.installer_scope = "raw-file-only"
        if zipfile.is_zipfile(installer):
            self.zip("installer", installer)
            self.installer_scope = "raw-file-and-zip-payload"

    def report(self):
        return {"passed": not self.findings, "rawAndDecodedItems": self.items,
                "codeObjects": self.code_objects, "archives": self.archives,
                "decodedBytes": self.decoded_bytes, "installerScope": self.installer_scope,
                "findings": [{"artifact": label, "category": category} for label, category in sorted(self.findings)]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--app", required=True, type=Path)
    parser.add_argument("--installer", type=Path)
    parser.add_argument("--forbid-prefix", action="append", default=[], help="Additional private build path; never printed")
    parser.add_argument("--forbidden-text", action="append", default=[], help="Additional private text; never printed")
    args = parser.parse_args()
    prefixes = {str(Path(__file__).resolve().parents[1]), str(Path.cwd()), str(Path.home()), *args.forbid_prefix}
    if os.environ.get("USERPROFILE"):
        prefixes.add(os.environ["USERPROFILE"])
    # Ignore root-only entries that would match every slash in arbitrary data.
    prefixes = {item.rstrip("/\\") for item in prefixes if len(item.rstrip("/\\")) > 3}
    inspector = Inspector(prefixes, args.forbidden_text)
    try:
        inspector.app(args.app.absolute())
        if args.installer:
            inspector.installer(args.installer.absolute())
    except Exception as exc:
        inspector.issue("inspection", "incomplete-inspection-" + type(exc).__name__)
    report = inspector.report()
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
