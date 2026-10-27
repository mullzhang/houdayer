"""The dimod sampler interface for bounded sample-pool expansion."""

from __future__ import annotations

import secrets
from time import perf_counter
from typing import Any

import dimod
import numpy as np

from . import _native
from ._validation import (
    DEFAULT_MAX_CANDIDATES,
    DEFAULT_MAX_NUM_SAMPLES,
    DEFAULT_MAX_PAIRS,
    prepare_inputs,
    validate_options,
)


class HoudayerExpander(dimod.Sampler):
    """Recombine existing SPIN/BINARY samples using disagreement components.

    This sampler requires initial states. It preserves the sum of the energies
    of complementary offspring, not each offspring's energy. Outputs are unique
    assignments with ``num_occurrences=1``, not measurements or Boltzmann samples.

    See ``docs/api.md`` and ``docs/algorithm.md`` for enumeration and budget semantics.
    """

    @property
    def parameters(self) -> dict[str, list[str]]:
        return {
            "initial_states": [],
            "max_num_samples": [],
            "max_pairs": [],
            "max_candidates": [],
            "seed": [],
            "include_initial_states": [],
        }

    @property
    def properties(self) -> dict[str, Any]:
        return {"algorithm": "houdayer", "version": _native.__version__}

    def sample(
        self,
        bqm: dimod.BinaryQuadraticModel,
        *,
        initial_states: Any = None,
        max_num_samples: int = DEFAULT_MAX_NUM_SAMPLES,
        max_pairs: int = DEFAULT_MAX_PAIRS,
        max_candidates: int = DEFAULT_MAX_CANDIDATES,
        seed: int | None = None,
        include_initial_states: bool = True,
        **kwargs: Any,
    ) -> dimod.SampleSet:
        """Expand a pool of existing samples within finite work budgets.

        Args:
            bqm: The objective used for topology and returned energies.
            initial_states: A nonempty SampleSet or dimod samples-like object.
                Values and labels must describe complete assignments. SampleSet
                vartypes are converted explicitly; raw samples use the BQM's domain.
            max_num_samples: Maximum unique pool size, including all unique inputs.
            max_pairs: Maximum number of parent pairs started across all rounds.
            max_candidates: Maximum non-parent candidates checked, including duplicates.
            seed: Unsigned 64-bit seed. None draws and records a fresh seed.
            include_initial_states: Include the deduplicated input rows in the output.
            **kwargs: Unknown keywords produce dimod's standard warnings.

        Returns:
            Unique samples in first-discovery order, with energies recomputed from
            bqm and execution statistics in ``info["houdayer"]``. Initial rows come first.

        Raises:
            ValueError: Invalid model, states, bounds, or a pool cap below the unique input size.
            TypeError: Invalid argument types.
            MemoryError: Native memory reservation fails.
            KeyboardInterrupt: Execution is interrupted; no partial result is returned.
        """
        start = perf_counter()
        self.remove_unknown_kwargs(**kwargs)
        options = validate_options(
            max_num_samples=max_num_samples,
            max_pairs=max_pairs,
            max_candidates=max_candidates,
            seed=seed,
            include_initial_states=include_initial_states,
        )
        samples, variables, edges = prepare_inputs(bqm, initial_states)
        if options["seed"] is None:
            options["seed"] = secrets.randbits(64)
        prepared = perf_counter()
        native = _native.expand_samples(samples, edges, **options)
        expanded = perf_counter()
        output = native["samples"]
        if bqm.vartype is dimod.BINARY:
            output = (output + 1) // 2
        energies = bqm.energies((output, variables), dtype=np.float64)
        if not np.isfinite(energies).all():
            raise ValueError("BQM energy evaluation produced a nonfinite result")
        info = native["info"]
        info.update(options)
        info["version"] = _native.__version__
        result = dimod.SampleSet.from_samples(
            (output, variables),
            vartype=bqm.vartype,
            energy=energies,
            num_occurrences=np.ones(len(output), dtype=np.int64),
            info={"houdayer": info},
            sort_labels=False,
        )
        result.info["houdayer"]["timing"] = {
            "preparation_seconds": prepared - start,
            "native_seconds": expanded - prepared,
            "result_seconds": perf_counter() - expanded,
        }
        return result
