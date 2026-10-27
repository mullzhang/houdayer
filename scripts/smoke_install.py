"""Exercise an installed distribution without importing from a source checkout."""

import importlib.metadata
import json
import sys
from pathlib import Path

import dimod
import houdayer
import numpy as np

assert Path(houdayer.__file__).resolve().is_relative_to(Path(sys.prefix).resolve())
assert houdayer.__version__ == importlib.metadata.version("houdayer")
bqm = dimod.BinaryQuadraticModel.from_ising({"a": 1, "b": -1}, {}, offset=3)
result = houdayer.HoudayerExpander().sample(
    bqm, initial_states=[{"a": -1, "b": -1}, {"a": 1, "b": 1}], seed=42
)
assert len(result) == 4
np.testing.assert_array_equal(result.record.energy, bqm.energies(result))
with houdayer.HoudayerComposite(dimod.ExactSolver()) as sampler:
    assert len(sampler.sample(bqm)) == 4
print(
    json.dumps(
        {
            "version": houdayer.__version__,
            "python": sys.version,
            "dimod": dimod.__version__,
            "numpy": np.__version__,
            "module": houdayer.__file__,
            "status": "passed",
        }
    )
)
