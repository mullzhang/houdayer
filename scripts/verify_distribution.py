"""Check archives, then install and test each in a clean external virtual environment."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
import zipfile
from datetime import datetime, timezone
from email.parser import BytesParser
from pathlib import Path, PurePosixPath


def run(command, *, cwd, env):
    completed = subprocess.run(command, cwd=cwd, env=env, capture_output=True, text=True)
    if completed.returncode:
        raise RuntimeError(f"Command failed: {command}\n{completed.stdout}\n{completed.stderr}")
    return completed.stdout.strip()


def inspect_archive(artifact: Path, root: Path) -> dict:
    wheel = artifact.suffix == ".whl"
    if wheel:
        with zipfile.ZipFile(artifact) as archive:
            files = {
                name: archive.read(name) for name in archive.namelist() if not name.endswith("/")
            }
        metadata_paths = [name for name in files if name.endswith(".dist-info/METADATA")]
        assert len(metadata_paths) == 1, "Wheel metadata missing or ambiguous"
        metadata = BytesParser().parsebytes(files[metadata_paths[0]])
        assert metadata["Name"] == "houdayer"
        assert metadata["License-Expression"] == "MIT"
        assert metadata["Requires-Python"] == ">=3.10"
        assert any("dimod" in value for value in metadata.get_all("Requires-Dist", []))
        assert any("numpy" in value for value in metadata.get_all("Requires-Dist", []))
        native = [
            name
            for name in files
            if name.startswith("houdayer/_native") and name.endswith((".so", ".pyd"))
        ]
        assert len(native) == 1, "Expected one native extension"
        required = ["houdayer/__init__.py", "houdayer/py.typed", "houdayer/_native.pyi"]
        assert any(name.endswith("/licenses/LICENSE") for name in files), "License missing"
        for source in (root / "python/houdayer").iterdir():
            if source.suffix in (".py", ".pyi") or source.name == "py.typed":
                assert files[f"houdayer/{source.name}"] == source.read_bytes()
    else:
        with tarfile.open(artifact, "r:gz") as archive:
            files = {}
            for member in archive.getmembers():
                if member.isfile():
                    stream = archive.extractfile(member)
                    assert stream is not None
                    files[
                        PurePosixPath(member.name)
                        .relative_to(PurePosixPath(member.name).parts[0])
                        .as_posix()
                    ] = stream.read()
                else:
                    assert member.isdir(), "Unexpected link or special archive member"
        required = [
            "pyproject.toml",
            "Cargo.toml",
            "Cargo.lock",
            "uv.lock",
            "README.md",
            "LICENSE",
            "rust/lib.rs",
            "python/houdayer/py.typed",
            "tests/reference.py",
            "scripts/smoke_install.py",
        ]
        for directory, pattern in [
            ("rust", "*.rs"),
            ("python", "*.py"),
            ("python", "*.pyi"),
            ("tests", "*.py"),
            ("scripts", "*.py"),
            ("examples", "*.py"),
            ("benchmarks", "*.py"),
            ("docs", "*.md"),
        ]:
            for source in (root / directory).rglob(pattern):
                relative = source.relative_to(root).as_posix()
                assert files[relative] == source.read_bytes(), (
                    f"Missing or stale source: {relative}"
                )
    for name in required:
        assert name in files, f"Missing distribution member: {name}"
    for name in files:
        parts = PurePosixPath(name).parts
        assert not set(parts).intersection({".venv", "target", ".git", "__pycache__"}), name
        assert not name.startswith("benchmarks/results/"), name
        assert not any(part.startswith(".env") for part in parts), name
        assert ".." not in parts and not name.startswith("/"), name
    return {
        "name": artifact.name,
        "sha256": hashlib.sha256(artifact.read_bytes()).hexdigest(),
        "members": len(files),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dist", type=Path)
    parser.add_argument(
        "--python", default=sys.executable, help="Interpreter used for clean installations"
    )
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    directory = args.dist.resolve()
    wheels = sorted(directory.glob("houdayer-*.whl"))
    sources = sorted(directory.glob("houdayer-*.tar.gz"))
    if len(wheels) != 1 or len(sources) != 1:
        parser.error(
            "expected exactly one local-platform wheel and one sdist; remove stale distributions"
        )
    uv = shutil.which("uv")
    if uv is None:
        parser.error("uv is required for isolated installation checks")
    environment = {
        k: v for k, v in os.environ.items() if k not in {"PYTHONPATH", "PYTHONHOME", "VIRTUAL_ENV"}
    }
    artifacts = wheels + sources
    report = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "python": args.python,
        "artifacts": [],
    }
    run(
        [sys.executable, "-m", "twine", "check", "--strict", *map(str, artifacts)],
        cwd=root,
        env=environment,
    )
    for artifact in artifacts:
        details = inspect_archive(artifact, root)
        with tempfile.TemporaryDirectory(prefix="houdayer-dist-") as temp:
            external = Path(temp)
            venv = external / "venv"
            run([uv, "venv", "--python", args.python, str(venv)], cwd=external, env=environment)
            executable = venv / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
            run(
                [uv, "pip", "install", "--python", str(executable), str(artifact), "pytest>=8,<10"],
                cwd=external,
                env=environment,
            )
            shutil.copy(root / "scripts/smoke_install.py", external / "smoke.py")
            shutil.copytree(
                root / "tests", external / "tests", ignore=shutil.ignore_patterns("__pycache__")
            )
            details["installation"] = json.loads(
                run([str(executable), "smoke.py"], cwd=external, env=environment)
            )
            details["tests"] = run(
                [str(executable), "-m", "pytest", "-q", "tests"], cwd=external, env=environment
            )
            details["examples"] = {}
            for example in sorted((root / "examples").glob("*.py")):
                shutil.copy(example, external / example.name)
                details["examples"][example.name] = run(
                    [str(executable), example.name], cwd=external, env=environment
                )
            print(f"Verified {artifact.name}: {details['tests'].splitlines()[-1]}")
        report["artifacts"].append(details)
    report["status"] = "passed"
    path = directory / "verification.json"
    path.write_text(json.dumps(report, indent=2) + "\n")
    print(f"Saved {path}")


if __name__ == "__main__":
    main()
