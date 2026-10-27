"""Run reproducible expansion workloads in fresh macOS/Linux processes."""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import subprocess
import sys
from datetime import datetime, timezone
from itertools import combinations
from pathlib import Path
from time import perf_counter

import dimod
import numpy as np
from houdayer import HoudayerExpander, __version__

CASES = {
    "small-independent": (8, 4, "independent"),
    "wide-independent": (128, 16, "independent"),
    "dimers": (128, 32, "dimers"),
    "chain": (256, 16, "chain"),
    "sparse": (1024, 16, "sparse"),
    "dense": (128, 32, "dense"),
}
OPTIONS = {"max_num_samples": 10000, "max_pairs": 10000, "max_candidates": 100000, "seed": 42}


def source_identity(root: Path) -> dict:
    paths = [root / name for name in ("Cargo.toml", "Cargo.lock", "pyproject.toml", "uv.lock")]
    for folder, pattern in [("rust", "*.rs"), ("python", "*.py"), ("benchmarks", "*.py")]:
        paths.extend((root / folder).rglob(pattern))
    fingerprints = {
        path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(paths)
    }
    commit = subprocess.run(["git", "rev-parse", "HEAD"], cwd=root, capture_output=True, text=True)
    status = subprocess.run(
        ["git", "status", "--porcelain"], cwd=root, capture_output=True, text=True
    )
    return {
        "files": fingerprints,
        "git_commit": commit.stdout.strip() if commit.returncode == 0 else None,
        "git_dirty": bool(status.stdout.strip()) if status.returncode == 0 else None,
    }


def make_case(name: str):
    n, reads, topology = CASES[name]
    rng = np.random.default_rng(12345)
    linear = rng.normal(size=n)
    if topology == "independent":
        edges = []
    elif topology == "dimers":
        edges = [(i, i + 1) for i in range(0, n, 2)]
    elif topology == "chain":
        edges = [(i, i + 1) for i in range(n - 1)]
    else:
        probability = 0.003 if topology == "sparse" else 0.3
        edges = [(i, j) for i, j in combinations(range(n), 2) if rng.random() < probability]
    quadratic = rng.normal(size=len(edges))
    bqm = dimod.BinaryQuadraticModel(dict(enumerate(linear)), {}, 1.25, dimod.SPIN)
    bqm.add_quadratic_from(dict(zip(edges, quadratic, strict=True)))
    initial = rng.choice([-1, 1], size=(reads, n)).astype(np.int8)
    return bqm, initial


def component_summary(bqm, initial):
    counts = []
    for a, b in combinations(initial, 2):
        remaining = {i for i in bqm.variables if a[i] != b[i]}
        count = 0
        while remaining:
            count += 1
            pending = [remaining.pop()]
            while pending:
                for other, bias in bqm.adj[pending.pop()].items():
                    if bias and other in remaining:
                        remaining.remove(other)
                        pending.append(other)
        counts.append(count)
    return {
        "min": min(counts),
        "max": max(counts),
        "mean": float(np.mean(counts)),
        "pairs": len(counts),
    }


def worker(name: str, artifact: Path) -> dict:
    import resource

    bqm, initial = make_case(name)
    components = component_summary(bqm, initial)
    start = perf_counter()
    result = HoudayerExpander().sample(bqm, initial_states=initial, **OPTIONS)
    elapsed = perf_counter() - start
    peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    peak_bytes = int(peak if sys.platform == "darwin" else peak * 1024)
    edges = list(bqm.quadratic)
    artifact.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(
        artifact,
        linear=np.array(list(bqm.linear.values())),
        edges=np.asarray(edges, dtype=np.int64).reshape(-1, 2),
        quadratic=np.array([bqm.quadratic[edge] for edge in edges]),
        offset=np.array(bqm.offset),
        initial=initial,
        output=result.record.sample,
        energies=result.record.energy,
    )
    return {
        "case": name,
        "num_variables": len(bqm),
        "num_edges": len(edges),
        "initial_components": components,
        "options": OPTIONS,
        "stats": result.info["houdayer"],
        "elapsed_seconds": elapsed,
        "peak_process_rss_bytes": peak_bytes,
        "artifact_sha256": hashlib.sha256(artifact.read_bytes()).hexdigest(),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--cases", nargs="+", choices=CASES, default=list(CASES))
    parser.add_argument("--worker", choices=CASES)
    parser.add_argument("--artifact", type=Path)
    args = parser.parse_args()
    if sys.platform not in ("darwin", "linux"):
        parser.error("this RSS benchmark runner requires macOS or Linux")
    if args.worker:
        if args.artifact is None:
            parser.error("--worker requires --artifact")
        print(json.dumps(worker(args.worker, args.artifact)))
        return
    if args.output is None:
        parser.error("--output is required")
    root = Path(__file__).resolve().parents[1]
    output = args.output.resolve()
    if output.exists():
        parser.error("output exists; choose a new path to preserve the previous run")
    artifact_dir = output.parent / f"{output.stem}-artifacts"
    artifact_dir.mkdir(parents=True, exist_ok=False)
    report = {
        "schema_version": 1,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "source": source_identity(root),
        "environment": {
            "platform": platform.platform(),
            "machine": platform.machine(),
            "python": sys.version,
            "houdayer": __version__,
            "numpy": np.__version__,
            "dimod": dimod.__version__,
        },
        "cases": [],
    }
    for name in args.cases:
        artifact = artifact_dir / f"{name}.npz"
        completed = subprocess.run(
            [
                sys.executable,
                str(Path(__file__).resolve()),
                "--worker",
                name,
                "--artifact",
                str(artifact),
            ],
            capture_output=True,
            text=True,
            check=True,
        )
        result = json.loads(completed.stdout)
        result["artifact"] = artifact.relative_to(output.parent).as_posix()
        report["cases"].append(result)
        output.write_text(json.dumps(report, indent=2) + "\n")
        print(
            f"{name}: {result['elapsed_seconds']:.4f}s, "
            f"{result['stats']['num_output_rows']} rows, {result['stats']['stop_reason']}"
        )
    report["status"] = "complete"
    output.write_text(json.dumps(report, indent=2) + "\n")


if __name__ == "__main__":
    main()
