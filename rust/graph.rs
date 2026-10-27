//! The nonzero interaction topology. Energies remain the Python BQM's responsibility.

use crate::RunError;

#[derive(Debug)]
pub struct Graph {
    pub(crate) adjacency: Vec<Vec<usize>>,
}

impl Graph {
    pub fn new<E>(num_variables: usize, edges: &[(usize, usize)]) -> Result<Self, RunError<E>> {
        let mut adjacency = Vec::new();
        adjacency.try_reserve_exact(num_variables)?;
        adjacency.resize_with(num_variables, Vec::new);
        for &(u, v) in edges {
            if u >= num_variables || v >= num_variables || u == v {
                return Err(RunError::InvalidInput("invalid edge endpoints"));
            }
            adjacency[u].try_reserve(1)?;
            adjacency[v].try_reserve(1)?;
            adjacency[u].push(v);
            adjacency[v].push(u);
        }
        // Stable traversal, regardless of the BQM's edge insertion order.
        for neighbors in &mut adjacency {
            neighbors.sort_unstable();
            neighbors.dedup();
        }
        Ok(Self { adjacency })
    }

    pub fn len(&self) -> usize {
        self.adjacency.len()
    }

    pub fn is_empty(&self) -> bool {
        self.adjacency.is_empty()
    }
}
