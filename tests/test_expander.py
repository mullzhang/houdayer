import copy
import importlib.metadata
from itertools import combinations, product

import dimod
import numpy as np
import pytest
from houdayer import HoudayerExpander, __version__
from reference import closure, pair_children


def assignments(samples):
    return {tuple(row) for row in samples.record.sample}


def unconnected(n, vartype=dimod.SPIN):
    return dimod.BinaryQuadraticModel({i: 0 for i in range(n)}, {}, 0, vartype)


def without_timing(result):
    return {k: v for k, v in result.info["houdayer"].items() if k != "timing"}


@pytest.mark.parametrize("edge_mask", range(8))
@pytest.mark.parametrize("vartype", [dimod.SPIN, dimod.BINARY])
def test_every_three_variable_parent_pair_against_exhaustive_oracle(edge_mask, vartype):
    edges = [(0, 1), (0, 2), (1, 2)]
    bqm = dimod.BinaryQuadraticModel(
        {0: 2, 1: -3, 2: 1},
        {
            edge: (-1) ** index * (index + 1)
            for index, edge in enumerate(edges)
            if edge_mask & (1 << index)
        },
        5,
        vartype,
    )
    rows = list(product(sorted(vartype.value), repeat=3))
    for a, b in combinations(rows, 2):
        result = HoudayerExpander().sample(
            bqm, initial_states=([a, b], list(bqm.variables)), max_pairs=1, seed=17
        )
        expected = pair_children(bqm, a, b)
        assert assignments(result) == expected
        np.testing.assert_array_equal(result.record.energy, bqm.energies(result))
        for child in expected:
            complement = tuple(x + y - z for x, y, z in zip(a, b, child, strict=True))
            energies = bqm.energies(([a, b, child, complement], list(bqm.variables)))
            assert energies[0] + energies[1] == energies[2] + energies[3]
        count = len(expected)
        assert result.info["houdayer"]["num_candidates"] == (count - 2 if count > 2 else 0)


@pytest.mark.parametrize("seed", range(10))
def test_random_graph_closure_matches_reference(seed):
    rng = np.random.default_rng(seed)
    bqm = dimod.BinaryQuadraticModel(
        {i: float(rng.normal()) for i in range(5)},
        {(i, j): float(rng.normal()) for i, j in combinations(range(5), 2) if rng.random() < 0.35},
        2.75,
        dimod.SPIN,
    )
    initial = rng.choice([-1, 1], (5, 5))
    result = HoudayerExpander().sample(
        bqm, initial_states=(initial, list(bqm.variables)), seed=seed
    )
    assert assignments(result) == closure(bqm, initial)
    assert result.info["houdayer"]["stop_reason"] == "exhausted"
    assert result.info["houdayer"]["num_pairs"] == len(result) * (len(result) - 1) // 2


def test_new_solutions_become_parents_only_in_later_rounds():
    bqm = unconnected(3, dimod.BINARY)
    seeds = [(0, 0, 0), (1, 1, 0), (1, 0, 1)]
    first_pass = set().union(*(pair_children(bqm, a, b) for a, b in combinations(seeds, 2)))
    assert (0, 1, 1) not in first_pass
    result = HoudayerExpander().sample(bqm, initial_states=seeds, seed=42)
    assert assignments(result) == set(product((0, 1), repeat=3))
    assert result.info["houdayer"]["num_rounds"] == 3


def test_exact_ground_states_stay_ground_states():
    bqm = dimod.BinaryQuadraticModel.from_ising(
        {i: 0 for i in range(4)}, {(0, 1): -1, (2, 3): -1}, offset=3
    )
    seeds = [[-1] * 4, [1] * 4]
    result = HoudayerExpander().sample(bqm, initial_states=seeds, seed=1)
    expected = dimod.ExactSolver().sample(bqm).lowest()
    assert assignments(result) == assignments(expected)
    np.testing.assert_array_equal(result.record.energy, np.ones(4))


def test_equal_energy_nonoptimal_parents_do_not_preserve_individual_energy():
    bqm = dimod.BinaryQuadraticModel.from_ising({0: 1, 1: 1}, {})
    result = HoudayerExpander().sample(bqm, initial_states=[[1, -1], [-1, 1]], seed=1)
    assert set(result.record.energy) == {-2, 0, 2}


def test_zero_field_also_does_not_imply_individual_energy_conservation():
    bqm = dimod.BinaryQuadraticModel.from_ising({0: 0, 1: 0, 2: 0}, {(0, 2): 1, (1, 2): 1})
    result = HoudayerExpander().sample(bqm, initial_states=[[1, -1, 1], [-1, 1, 1]], seed=2)
    assert set(result.record.energy) == {-2, 0, 2}


def test_zero_edges_are_ignored_but_subnormal_edges_are_kept():
    for bias, count in [(0.0, 4), (np.nextafter(0.0, 1.0), 2)]:
        bqm = dimod.BinaryQuadraticModel({0: 0, 1: 0}, {(0, 1): bias}, 0, dimod.BINARY)
        result = HoudayerExpander().sample(bqm, initial_states=[[0, 0], [1, 1]], seed=1)
        assert len(result) == count


def test_labels_column_order_offset_and_no_input_mutation():
    labels = ["z", ("tuple", 2), 7]
    bqm = dimod.BinaryQuadraticModel(
        {label: i + 0.25 for i, label in enumerate(labels)}, {}, 4.5, dimod.SPIN
    )
    seeds = dimod.SampleSet.from_samples(
        (np.array([[1, -1, 1], [-1, 1, -1]]), list(reversed(labels))),
        vartype=dimod.SPIN,
        energy=[999, 888],
        num_occurrences=[20, 30],
        chain_break_fraction=[0.1, 0.3],
        info={"original": [1, 2]},
        sort_labels=False,
    )
    original_bqm = bqm.copy()
    original = seeds.copy()
    result = HoudayerExpander().sample(bqm, initial_states=seeds, seed=42)
    assert list(result.variables) == labels
    np.testing.assert_array_equal(result.record.energy, bqm.energies(result))
    assert np.all(result.record.num_occurrences == 1)
    assert "chain_break_fraction" not in result.record.dtype.names
    assert seeds == original
    assert bqm == original_bqm


@pytest.mark.parametrize("vartype", [dimod.SPIN, dimod.BINARY])
def test_sampleset_vartype_conversion_is_explicit(vartype):
    bqm = unconnected(2, vartype)
    opposite = dimod.BINARY if vartype is dimod.SPIN else dimod.SPIN
    low, high = sorted(opposite.value)
    seeds = dimod.SampleSet.from_samples([[low, low], [high, high]], opposite, energy=[123, 456])
    result = HoudayerExpander().sample(bqm, initial_states=seeds, seed=1)
    assert result.vartype is vartype
    assert assignments(result) == set(product(sorted(vartype.value), repeat=2))
    assert seeds.vartype is opposite


def test_duplicate_inputs_keep_first_occurrence_order_and_discard_frequencies():
    seeds = dimod.SampleSet.from_samples(
        [[1, 1], [-1, -1], [1, 1]], dimod.SPIN, energy=[1, 2, 1], num_occurrences=[6, 4, 9]
    )
    result = HoudayerExpander().sample(unconnected(2), initial_states=seeds, seed=1)
    np.testing.assert_array_equal(result.record.sample[:2], [[1, 1], [-1, -1]])
    assert result.info["houdayer"]["num_input_rows"] == 3
    assert result.info["houdayer"]["num_initial_states"] == 2
    assert result.info["houdayer"]["num_new_states"] == 2
    assert np.all(result.record.num_occurrences == 1)


@pytest.mark.parametrize(
    "options,reason,size",
    [
        ({"max_num_samples": 2}, "sample_limit", 2),
        ({"max_num_samples": 7}, "sample_limit", 7),
        ({"max_pairs": 0}, "pair_limit", 2),
        ({"max_pairs": 1}, "pair_limit", 256),
        ({"max_candidates": 0}, "candidate_limit", 2),
        ({"max_candidates": 5}, "candidate_limit", 7),
        ({"max_num_samples": 7, "max_candidates": 5, "max_pairs": 1}, "sample_limit", 7),
        ({"max_candidates": 5, "max_pairs": 1}, "candidate_limit", 7),
    ],
)
def test_budget_limits_and_precedence(options, reason, size):
    result = HoudayerExpander().sample(
        unconnected(8), initial_states=[[-1] * 8, [1] * 8], seed=42, **options
    )
    info = result.info["houdayer"]
    assert len(result) == size
    assert info["stop_reason"] == reason
    assert info["num_pairs"] <= info["max_pairs"]
    assert info["num_candidates"] <= info["max_candidates"]


def test_duplicate_candidates_consume_the_candidate_budget():
    seeds = list(product((-1, 1), repeat=4))
    result = HoudayerExpander().sample(
        unconnected(4), initial_states=seeds, max_candidates=5, seed=4
    )
    info = result.info["houdayer"]
    assert len(result) == len(seeds)
    assert info["num_candidates"] == info["num_duplicates"] == 5
    assert info["stop_reason"] == "candidate_limit"


def test_more_than_machine_word_components_are_bounded():
    result = HoudayerExpander().sample(
        unconnected(130), initial_states=[[-1] * 130, [1] * 130], max_candidates=9, seed=42
    )
    assert len(result) == 11
    assert result.info["houdayer"]["num_candidates"] == 9


@pytest.mark.parametrize("initial,expected", [([[1, -1]], 1), ([[1, -1], [1, -1]], 1)])
def test_single_unique_state_is_a_valid_noop(initial, expected):
    result = HoudayerExpander().sample(unconnected(2), initial_states=initial, seed=1)
    assert len(result) == expected
    assert result.info["houdayer"]["stop_reason"] == "insufficient_unique_states"


@pytest.mark.parametrize("include", [False, True])
def test_zero_variable_model_and_empty_output_shape(include):
    bqm = dimod.BinaryQuadraticModel({}, {}, 2.5, dimod.BINARY)
    result = HoudayerExpander().sample(
        bqm, initial_states=[{}, {}], include_initial_states=include, seed=1
    )
    assert result.record.sample.shape == (int(include), 0)
    assert len(result.variables) == 0
    assert result.vartype is dimod.BINARY
    np.testing.assert_array_equal(result.record.energy, [2.5] if include else [])


def test_only_new_states_and_cap_always_includes_initial_states():
    bqm = unconnected(3)
    result = HoudayerExpander().sample(
        bqm,
        initial_states=[[-1] * 3, [1] * 3],
        include_initial_states=False,
        max_num_samples=4,
        seed=2,
    )
    assert len(result) == 2
    assert not assignments(result).intersection({(-1,) * 3, (1,) * 3})
    empty = HoudayerExpander().sample(bqm, initial_states=[[-1] * 3], include_initial_states=False)
    assert empty.record.sample.shape == (0, 3)
    with pytest.raises(ValueError, match="smaller"):
        HoudayerExpander().sample(
            bqm, initial_states=[[-1] * 3, [1] * 3], include_initial_states=False, max_num_samples=1
        )


def test_fixed_and_generated_seeds_are_replayable():
    bqm = unconnected(10)
    options = {"initial_states": [[-1] * 10, [1] * 10], "max_candidates": 12}
    for seed in [None, 0, 42, 2**64 - 1, np.int64(123)]:
        first = HoudayerExpander().sample(bqm, seed=seed, **options)
        second = HoudayerExpander().sample(bqm, seed=first.info["houdayer"]["seed"], **options)
        np.testing.assert_array_equal(first.record, second.record)
        assert without_timing(first) == without_timing(second)
    a = HoudayerExpander().sample(bqm, seed=11, **options)
    b = HoudayerExpander().sample(bqm, seed=22, **options)
    assert assignments(a) != assignments(b)


def test_spin_and_binary_representation_give_equivalent_results():
    spin = dimod.BinaryQuadraticModel.from_ising(
        {0: 0.25, 1: -0.5, 2: 0.75}, {(0, 1): 1.25}, offset=3.5
    )
    binary = spin.change_vartype(dimod.BINARY, inplace=False)
    states = np.array(list(product((-1, 1), repeat=3)), dtype=np.int8)[[0, 7, 2]]
    a = HoudayerExpander().sample(spin, initial_states=states, seed=42)
    b = HoudayerExpander().sample(binary, initial_states=(states + 1) // 2, seed=42)
    np.testing.assert_array_equal(a.record.sample, b.record.sample * 2 - 1)
    np.testing.assert_allclose(a.record.energy, b.record.energy, rtol=0, atol=1e-12)


def test_dimod_mixins_contract_warnings_and_package_metadata():
    sampler = HoudayerExpander()
    dimod.testing.assert_sampler_api(sampler)
    with pytest.warns(dimod.exceptions.SamplerUnknownArgWarning):
        sampler.sample(unconnected(1), initial_states=[[1]], num_reads=9)
    ising = sampler.sample_ising({0: 0, 1: 0}, {}, initial_states=[[-1, -1], [1, 1]], seed=1)
    qubo = sampler.sample_qubo({(0, 0): 0, (1, 1): 0}, initial_states=[[0, 0], [1, 1]], seed=1)
    assert len(ising) == len(qubo) == 4
    assert __version__ == importlib.metadata.version("houdayer")


@pytest.mark.parametrize(
    "initial",
    [
        None,
        [],
        np.empty((0, 2)),
        [[0, 1]],
        [[1.25, -1]],
        [[256, -1]],
        [[np.nan, -1]],
        [[np.inf, -1]],
        [[1 + 0j, -1]],
        [["1", "-1"]],
        [{0: 1}],
        [{0: 1, 1: -1, 2: 1}],
        ([[1, -1]], [0, 0]),
    ],
)
def test_invalid_states_are_rejected_before_casting(initial):
    with pytest.raises((ValueError, TypeError)):
        HoudayerExpander().sample(unconnected(2), initial_states=initial)


@pytest.mark.parametrize(
    "name,value,error",
    [
        ("max_num_samples", 0, ValueError),
        ("max_pairs", -1, ValueError),
        ("max_candidates", -1, ValueError),
        ("max_num_samples", 1.5, TypeError),
        ("max_pairs", True, TypeError),
        ("max_candidates", None, TypeError),
        ("seed", -1, ValueError),
        ("seed", 2**64, ValueError),
        ("seed", True, TypeError),
        ("include_initial_states", 1, TypeError),
        ("include_initial_states", "false", TypeError),
        ("max_num_samples", 2**80, ValueError),
    ],
)
def test_invalid_options(name, value, error):
    with pytest.raises(error):
        HoudayerExpander().sample(
            unconnected(2), initial_states=[[-1, -1], [1, 1]], **{name: value}
        )


@pytest.mark.parametrize("bias", [np.nan, np.inf, -np.inf, np.finfo(float).max])
@pytest.mark.parametrize("location", ["linear", "quadratic", "offset"])
def test_invalid_or_overflowing_energies(bias, location):
    bqm = unconnected(2)
    bqm.offset = np.finfo(float).max if bias == np.finfo(float).max else 0
    if location == "linear":
        bqm.set_linear(0, bias)
    elif location == "quadratic":
        bqm.add_quadratic(0, 1, bias)
    else:
        bqm.offset = bias
        if bias == np.finfo(float).max:
            bqm.set_linear(0, bias)
    with pytest.raises(ValueError, match="finite"):
        HoudayerExpander().sample(bqm, initial_states=[[-1, -1], [1, 1]])


def test_parameter_and_property_dicts_cannot_change_the_sampler():
    sampler = HoudayerExpander()
    expected = copy.deepcopy(sampler.parameters)
    sampler.parameters.clear()
    sampler.properties.clear()
    assert sampler.parameters == expected
    assert sampler.properties["version"] == __version__
