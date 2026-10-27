"""Shared option validation and label-preserving conversion to native inputs."""

from __future__ import annotations

import math
import operator
import sys
from itertools import chain
from typing import Any

import dimod
import numpy as np
import numpy.typing as npt

DEFAULT_MAX_NUM_SAMPLES = 10_000
DEFAULT_MAX_PAIRS = 10_000
DEFAULT_MAX_CANDIDATES = 100_000


def _integer(name: str, value: Any, minimum: int, maximum: int) -> int:
    if isinstance(value, (bool, np.bool_)):
        raise TypeError(f"{name} must be an integer, not a boolean")
    try:
        number = operator.index(value)
    except TypeError as error:
        raise TypeError(f"{name} must be an integer") from error
    if not minimum <= number <= maximum:
        raise ValueError(f"{name} must be between {minimum} and {maximum}")
    return number


def validate_options(
    *,
    max_num_samples: int = DEFAULT_MAX_NUM_SAMPLES,
    max_pairs: int = DEFAULT_MAX_PAIRS,
    max_candidates: int = DEFAULT_MAX_CANDIDATES,
    seed: int | None = None,
    include_initial_states: bool = True,
) -> dict[str, Any]:
    """Validate without drawing a seed or running the child sampler."""
    if not isinstance(include_initial_states, (bool, np.bool_)):
        raise TypeError("include_initial_states must be a boolean")
    return {
        "max_num_samples": _integer("max_num_samples", max_num_samples, 1, sys.maxsize),
        "max_pairs": _integer("max_pairs", max_pairs, 0, sys.maxsize),
        "max_candidates": _integer("max_candidates", max_candidates, 0, sys.maxsize),
        "seed": None if seed is None else _integer("seed", seed, 0, 2**64 - 1),
        "include_initial_states": bool(include_initial_states),
    }


def prepare_inputs(
    bqm: dimod.BinaryQuadraticModel,
    initial_states: Any,
) -> tuple[npt.NDArray[np.int8], list[Any], list[tuple[int, int]]]:
    """Validate values before integer conversion, then copy into the BQM's column order."""
    if not isinstance(bqm, dimod.BinaryQuadraticModel):
        raise TypeError("bqm must be a dimod.BinaryQuadraticModel")
    if initial_states is None:
        raise ValueError("initial_states is required; no random initial states are generated")
    try:
        bound = math.fsum(
            abs(float(bias))
            for bias in chain([bqm.offset], bqm.linear.values(), bqm.quadratic.values())
        )
    except (OverflowError, ValueError) as error:
        raise ValueError("BQM biases and their absolute sum must be finite") from error
    if not math.isfinite(bound):
        raise ValueError("BQM biases and their absolute sum must be finite")

    input_vartype = (
        initial_states.vartype if isinstance(initial_states, dimod.SampleSet) else bqm.vartype
    )
    if input_vartype not in (dimod.SPIN, dimod.BINARY):
        raise ValueError("initial_states must have SPIN or BINARY vartype")
    values, labels = dimod.as_samples(initial_states)
    if values.shape[0] == 0:
        raise ValueError("initial_states must contain at least one sample")
    variables = list(bqm.variables)
    if len(labels) != len(variables) or set(labels) != set(variables):
        raise ValueError("initial_states must contain exactly the BQM's variables")
    if values.dtype.kind not in "biuf" or not np.isin(values, tuple(input_vartype.value)).all():
        raise ValueError("initial_states contains values outside its SPIN or BINARY domain")
    positions = {label: index for index, label in enumerate(labels)}
    samples = np.array(
        values[:, [positions[label] for label in variables]], dtype=np.int8, order="C", copy=True
    )
    if input_vartype is dimod.BINARY:
        samples *= 2
        samples -= 1
    indices = {label: index for index, label in enumerate(variables)}
    # Topology is unchanged by BINARY/SPIN conversion. Retain even subnormal nonzero biases.
    edges = [(indices[u], indices[v]) for (u, v), bias in bqm.quadratic.items() if bias != 0]
    return samples, variables, edges
