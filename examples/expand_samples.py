"""Expand two ground states of disconnected ferromagnetic dimers."""

import dimod
from houdayer import HoudayerExpander

bqm = dimod.BinaryQuadraticModel.from_ising(
    {"a": 0, "b": 0, "c": 0, "d": 0},
    {("a", "b"): -1, ("c", "d"): -1},
    offset=0.5,
)
initial = dimod.SampleSet.from_samples(
    [{v: -1 for v in bqm.variables}, {v: 1 for v in bqm.variables}],
    vartype=dimod.SPIN,
    energy=[-1.5, -1.5],
)
expanded = HoudayerExpander().sample(bqm, initial_states=initial, seed=42)
assert len(expanded) == 4
assert all(expanded.record.energy == -1.5)
print(expanded)
print(expanded.info["houdayer"])
