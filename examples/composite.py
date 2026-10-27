"""Compose an existing dimod sampler with bounded expansion."""

import dimod
from houdayer import HoudayerComposite

bqm = dimod.BinaryQuadraticModel({v: 0.0 for v in range(6)}, {}, 0.0, dimod.BINARY)
with HoudayerComposite(
    dimod.RandomSampler(),
    expansion_parameters={"max_num_samples": 64, "seed": 42},
) as sampler:
    expanded = sampler.sample(bqm, num_reads=8, seed=7)

assert len(expanded) <= 64
assert expanded.vartype is dimod.BINARY
assert all(expanded.record.energy == 0)
assert "child_info" in expanded.info
print(expanded.info["houdayer"])
