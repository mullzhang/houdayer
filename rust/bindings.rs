//! The private NumPy / PyO3 boundary. No Python objects enter the expansion loop.

use numpy::{PyArray2, PyReadonlyArray2, PyUntypedArrayMethods, ndarray::Array2};
use pyo3::{
    exceptions::{PyMemoryError, PyValueError},
    prelude::*,
    types::PyDict,
};

use crate::{Config, Graph, RunError, expand};

fn python_error(error: RunError<PyErr>) -> PyErr {
    match error {
        RunError::InvalidInput(message) => PyValueError::new_err(message),
        RunError::SizeOverflow => {
            PyValueError::new_err("requested sample dimensions exceed addressable memory")
        }
        RunError::Allocation(error) => PyMemoryError::new_err(error.to_string()),
        RunError::Interrupted(error) => error,
    }
}

#[pyfunction]
#[allow(clippy::too_many_arguments)]
fn expand_samples<'py>(
    py: Python<'py>,
    initial_states: PyReadonlyArray2<'py, i8>,
    edges: Vec<(usize, usize)>,
    max_num_samples: usize,
    max_pairs: usize,
    max_candidates: usize,
    seed: u64,
    include_initial_states: bool,
) -> PyResult<Bound<'py, PyDict>> {
    let shape = initial_states.shape();
    let (num_rows, n) = (shape[0], shape[1]);
    let mut owned = Vec::new();
    owned
        .try_reserve_exact(initial_states.len())
        .map_err(|e| PyMemoryError::new_err(e.to_string()))?;
    owned.extend(initial_states.as_array().iter().copied());
    let config = Config {
        max_num_samples,
        max_pairs,
        max_candidates,
        seed,
        include_initial_states,
    };
    let output = py
        .detach(|| {
            let graph = Graph::new(n, &edges)?;
            expand(&graph, &owned, num_rows, &config, || {
                Python::attach(|py| py.check_signals())
            })
        })
        .map_err(python_error)?;
    let stats = output.stats;
    let array = Array2::from_shape_vec((stats.num_output_rows, n), output.samples)
        .map_err(|e| PyValueError::new_err(e.to_string()))?;
    let result = PyDict::new(py);
    result.set_item("samples", PyArray2::from_owned_array(py, array))?;
    let info = PyDict::new(py);
    info.set_item("num_input_rows", stats.num_input_rows)?;
    info.set_item("num_initial_states", stats.num_initial_states)?;
    info.set_item("num_new_states", stats.num_new_states)?;
    info.set_item("num_output_rows", stats.num_output_rows)?;
    info.set_item("num_pairs", stats.num_pairs)?;
    info.set_item("num_candidates", stats.num_candidates)?;
    info.set_item("num_duplicates", stats.num_duplicates)?;
    info.set_item("num_rounds", stats.num_rounds)?;
    info.set_item("stop_reason", output.stop_reason.as_str())?;
    result.set_item("info", info)?;
    Ok(result)
}

#[pymodule]
fn _native(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add("__version__", env!("CARGO_PKG_VERSION"))?;
    module.add_function(wrap_pyfunction!(expand_samples, module)?)?;
    Ok(())
}
