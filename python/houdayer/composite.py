"""Attach bounded Houdayer postprocessing to a dimod sampler."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import dimod

from ._validation import validate_options
from .expander import HoudayerExpander


class HoudayerComposite(dimod.ComposedSampler):
    """Run a child sampler once, then expand its output.

    Expansion options belong to the constructor. All ``sample`` keyword arguments,
    including ``seed`` and ``num_reads``, belong to the child. The expansion seed is
    ``expansion_parameters["seed"]``. The child retains its own graph restrictions.
    """

    def __init__(
        self,
        child_sampler: dimod.Sampler,
        *,
        expansion_parameters: Mapping[str, Any] | None = None,
    ) -> None:
        if not isinstance(child_sampler, dimod.Sampler):
            raise TypeError("child_sampler must be a dimod.Sampler")
        if expansion_parameters is None:
            expansion_parameters = {}
        if not isinstance(expansion_parameters, Mapping):
            raise TypeError("expansion_parameters must be a mapping")
        supplied = dict(expansion_parameters)
        if "initial_states" in supplied:
            raise ValueError("initial_states is provided by the child sampler")
        self._expansion_parameters = validate_options(**supplied)
        self._children = [child_sampler]
        self._expander = HoudayerExpander()

    @property
    def children(self) -> list[dimod.Sampler]:
        return self._children.copy()

    @property
    def parameters(self) -> dict[str, list[str]]:
        return {key: list(value) for key, value in self.child.parameters.items()}

    @property
    def properties(self) -> dict[str, Any]:
        return {
            "child_properties": self.child.properties.copy(),
            "expansion_parameters": self._expansion_parameters.copy(),
        }

    def sample(self, bqm: dimod.BinaryQuadraticModel, **parameters: Any) -> dimod.SampleSet:
        """Sample the child with its own parameters, then return an expanded SampleSet.

        Child metadata is shallow-copied into ``info["child_info"]``. Per-row child
        fields and measurement frequencies are not attached to generated samples.
        """
        initial_states = self.child.sample(bqm, **parameters)
        expanded = self._expander.sample(
            bqm, initial_states=initial_states, **self._expansion_parameters
        )
        expanded.info["child_info"] = initial_states.info.copy()
        return expanded
