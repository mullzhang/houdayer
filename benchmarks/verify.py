"""Audit saved benchmark outputs and replay their exact inputs and budgets."""

import argparse
import hashlib
import json
from pathlib import Path

import dimod
import numpy as np
from houdayer import HoudayerExpander
from run import source_identity


def verify(path: Path):
    report = json.loads(path.read_text())
    assert report["schema_version"] == 1 and report["status"] == "complete"
    root = Path(__file__).resolve().parents[1]
    assert report["source"]["files"] == source_identity(root)["files"], (
        "Implementation or runner changed; record a new run"
    )
    for case in report["cases"]:
        artifact = path.parent / case["artifact"]
        assert hashlib.sha256(artifact.read_bytes()).hexdigest() == case["artifact_sha256"]
        with np.load(artifact, allow_pickle=False) as data:
            bqm = dimod.BinaryQuadraticModel(
                dict(enumerate(data["linear"])),
                {},
                float(data["offset"]),
                dimod.SPIN,
            )
            bqm.add_quadratic_from(
                {
                    tuple(edge): weight
                    for edge, weight in zip(data["edges"], data["quadratic"], strict=True)
                }
            )
            result = HoudayerExpander().sample(
                bqm, initial_states=data["initial"], **case["options"]
            )
            np.testing.assert_array_equal(result.record.sample, data["output"])
            np.testing.assert_allclose(
                data["energies"],
                bqm.energies((data["output"], list(bqm.variables))),
                rtol=1e-12,
                atol=1e-12,
            )
            assert len({tuple(row) for row in data["output"]}) == len(result)
            for key, value in case["stats"].items():
                if key != "timing":
                    assert result.info["houdayer"][key] == value, key
        print(f"Verified {case['case']}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("report", type=Path)
    verify(parser.parse_args().report.resolve())
