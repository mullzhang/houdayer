from typing import Any

import numpy as np
import numpy.typing as npt

__version__: str

def expand_samples(
    initial_states: npt.NDArray[np.int8],
    edges: list[tuple[int, int]],
    max_num_samples: int,
    max_pairs: int,
    max_candidates: int,
    seed: int,
    include_initial_states: bool,
) -> dict[str, Any]: ...
