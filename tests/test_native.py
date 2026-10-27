import os
import subprocess
import sys
import textwrap

import numpy as np
import pytest
from houdayer import _native


def test_noncontiguous_native_input_is_copied_in_logical_row_order():
    backing = np.array([[-1, 8, -1, 9], [1, 8, 1, 9]], dtype=np.int8)
    result = _native.expand_samples(backing[:, ::2], [], 10, 10, 100, 42, True)
    assert set(map(tuple, result["samples"])) == {(-1, -1), (1, 1), (-1, 1), (1, -1)}
    np.testing.assert_array_equal(backing[:, 1::2], [[8, 9], [8, 9]])


def test_native_input_validation_is_not_only_a_python_wrapper_check():
    states = np.array([[-1, -1], [1, 1]], dtype=np.int8)
    for edges in [[(0, 2)], [(1, 1)]]:
        with pytest.raises(ValueError, match="endpoints"):
            _native.expand_samples(states, edges, 10, 10, 100, 1, True)
    with pytest.raises(ValueError, match="values"):
        _native.expand_samples(np.array([[0, 1]], dtype=np.int8), [], 10, 10, 100, 1, True)
    with pytest.raises(ValueError, match="memory"):
        _native.expand_samples(states, [], sys.maxsize, 10, 100, 1, True)


@pytest.mark.skipif(os.name != "posix", reason="Uses POSIX SIGINT delivery")
def test_native_expansion_releases_gil_and_responds_to_sigint():
    program = textwrap.dedent("""
        import os
        import signal
        import threading
        import time
        import numpy as np
        from houdayer import _native

        def interrupt():
            time.sleep(0.05)
            os.kill(os.getpid(), signal.SIGINT)

        states = np.array([[-1] * 128, [1] * 128], dtype=np.int8)
        thread = threading.Thread(target=interrupt, daemon=True)
        thread.start()
        try:
            _native.expand_samples(states, [], 1000000, 1000000, 1000000000, 42, True)
        except KeyboardInterrupt:
            print("interrupted")
        else:
            raise AssertionError("expansion ended before the interrupt")
    """)
    completed = subprocess.run(
        [sys.executable, "-c", program], capture_output=True, text=True, timeout=10
    )
    assert completed.returncode == 0, completed.stderr
    assert completed.stdout.strip() == "interrupted"
