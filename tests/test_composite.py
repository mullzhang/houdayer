from concurrent.futures import Future

import dimod
import numpy as np
import pytest
from houdayer import HoudayerComposite, HoudayerExpander


class RecordingSampler(dimod.Sampler):
    parameters = {"num_reads": [], "seed": [], "max_pairs": [], "initial_states": []}
    properties = {"description": "Recording child"}

    def __init__(self):
        self.calls = []
        self.closed = False
        self.result = dimod.SampleSet.from_samples(
            [[-1, -1], [1, 1]],
            dimod.SPIN,
            energy=[99, 99],
            num_occurrences=[50, 70],
            chain_break_fraction=[0.1, 0.2],
            info={"child": {"seed": 7}},
        )

    def sample(self, bqm, **kwargs):
        self.remove_unknown_kwargs(**kwargs)
        self.calls.append((bqm, kwargs))
        return self.result

    def close(self):
        self.closed = True


def model():
    return dimod.BinaryQuadraticModel.from_ising({0: 1, 1: -2}, {}, offset=4)


def test_composite_matches_explicit_calls_and_preserves_child_options():
    child = RecordingSampler()
    options = {"max_num_samples": 4, "seed": 42}
    sampler = HoudayerComposite(child, expansion_parameters=options)
    options["max_num_samples"] = 2
    result = sampler.sample(
        model(), num_reads=120, seed=7, max_pairs=13, initial_states="child-specific"
    )
    assert child.calls[0][1] == {
        "num_reads": 120,
        "seed": 7,
        "max_pairs": 13,
        "initial_states": "child-specific",
    }
    assert len(child.calls) == 1
    expected = HoudayerExpander().sample(
        model(), initial_states=child.result, max_num_samples=4, seed=42
    )
    np.testing.assert_array_equal(result.record, expected.record)
    assert result.info["child_info"] == child.result.info
    assert result.info["child_info"] is not child.result.info
    assert "chain_break_fraction" not in result.record.dtype.names
    np.testing.assert_array_equal(child.result.record.energy, [99, 99])


def test_dimod_composite_contract_and_context_manager_close():
    child = RecordingSampler()
    with HoudayerComposite(child) as sampler:
        dimod.testing.assert_sampler_api(sampler)
        dimod.testing.assert_composite_api(sampler)
        assert sampler.child is child
        assert sampler.parameters == child.parameters
        assert sampler.properties["child_properties"] == child.properties
        sampler.children.clear()
        assert sampler.child is child
        assert not child.closed
    assert child.closed


@pytest.mark.parametrize(
    "parameters,error",
    [
        ({"initial_states": []}, ValueError),
        ({"max_pairs": -1}, ValueError),
        ({"max_paiers": 4}, TypeError),
        ({"num_reads": 4}, TypeError),
        ([], TypeError),
    ],
)
def test_invalid_expansion_settings_fail_before_child_execution(parameters, error):
    child = RecordingSampler()
    with pytest.raises(error):
        HoudayerComposite(child, expansion_parameters=parameters)
    assert not child.calls


def test_invalid_child_and_child_exceptions_are_visible():
    with pytest.raises(TypeError, match="dimod.Sampler"):
        HoudayerComposite(object())
    child = RecordingSampler()

    def fail(*args, **kwargs):
        raise RuntimeError("child failed")

    child.sample = fail
    with pytest.raises(RuntimeError, match="child failed"):
        HoudayerComposite(child).sample(model())


def test_future_backed_sampleset_is_resolved():
    child = RecordingSampler()
    future = Future()
    future.set_result(child.result)
    child.result = dimod.SampleSet.from_future(future)
    result = HoudayerComposite(child).sample(model())
    assert len(result) == 4


def test_real_sampler_mixins_and_unknown_keyword_warning():
    bqm = model()
    with HoudayerComposite(dimod.ExactSolver()) as sampler:
        result = sampler.sample(bqm)
        assert len(result) == 4
        with pytest.warns(dimod.exceptions.SamplerUnknownArgWarning):
            sampler.sample_ising({0: 1}, {}, unsupported=True)


def test_empty_child_output_is_rejected_without_random_seeding():
    child = RecordingSampler()
    child.result = dimod.SampleSet.from_samples(
        (np.empty((0, 2), dtype=np.int8), [0, 1]), dimod.SPIN, energy=[]
    )
    with pytest.raises(ValueError, match="at least one"):
        HoudayerComposite(child).sample(model())
