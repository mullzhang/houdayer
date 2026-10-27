"""Small exhaustive oracle; deliberately independent of the native traversal."""

from itertools import combinations, product

import dimod


def pair_children(bqm: dimod.BinaryQuadraticModel, a: tuple, b: tuple) -> set[tuple]:
    variables = list(bqm.variables)
    indices = {variable: index for index, variable in enumerate(variables)}
    remaining = {i for i in range(len(variables)) if a[i] != b[i]}
    components = []
    while remaining:
        component = {min(remaining)}
        pending = list(component)
        remaining.difference_update(component)
        while pending:
            index = pending.pop()
            for variable, bias in bqm.adj[variables[index]].items():
                other = indices[variable]
                if bias and other in remaining:
                    remaining.remove(other)
                    component.add(other)
                    pending.append(other)
        components.append(component)
    children = set()
    for choices in product((False, True), repeat=len(components)):
        row = list(a)
        for component, use_b in zip(components, choices, strict=True):
            if use_b:
                for index in component:
                    row[index] = b[index]
        children.add(tuple(row))
    return children


def closure(bqm: dimod.BinaryQuadraticModel, seeds) -> set[tuple]:
    pool = {tuple(row) for row in seeds}
    while True:
        expanded = set(pool)
        for a, b in combinations(pool, 2):
            expanded.update(pair_children(bqm, a, b))
        if expanded == pool:
            return pool
        pool = expanded
