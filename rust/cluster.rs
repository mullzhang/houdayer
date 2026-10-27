//! Reusable BFS buffers for all disagreement components of a pair.

use crate::{Graph, RunError};

pub(crate) struct ClusterWorkspace {
    visited: Vec<bool>,
    pub sites: Vec<usize>,
    pub offsets: Vec<usize>,
}

impl ClusterWorkspace {
    pub fn new<E>(n: usize) -> Result<Self, RunError<E>> {
        let mut visited = Vec::new();
        visited.try_reserve_exact(n)?;
        visited.resize(n, false);
        let mut sites = Vec::new();
        sites.try_reserve_exact(n)?;
        let mut offsets = Vec::new();
        offsets.try_reserve_exact(n.checked_add(1).ok_or(RunError::SizeOverflow)?)?;
        Ok(Self {
            visited,
            sites,
            offsets,
        })
    }

    pub fn find<E>(
        &mut self,
        graph: &Graph,
        a: &[i8],
        b: &[i8],
        check_interrupt: &mut impl FnMut() -> Result<(), E>,
    ) -> Result<(), RunError<E>> {
        self.visited.fill(false);
        self.sites.clear();
        self.offsets.clear();
        let mut work = 0usize;
        for root in 0..graph.len() {
            if root % 4096 == 0 {
                check_interrupt().map_err(RunError::Interrupted)?;
            }
            if self.visited[root] || a[root] == b[root] {
                continue;
            }
            self.offsets.push(self.sites.len());
            self.visited[root] = true;
            self.sites.push(root);
            let mut cursor = self.sites.len() - 1;
            while cursor < self.sites.len() {
                for &neighbor in &graph.adjacency[self.sites[cursor]] {
                    if !self.visited[neighbor] && a[neighbor] != b[neighbor] {
                        self.visited[neighbor] = true;
                        self.sites.push(neighbor);
                    }
                    work += 1;
                    if work == 4096 {
                        check_interrupt().map_err(RunError::Interrupted)?;
                        work = 0;
                    }
                }
                cursor += 1;
            }
        }
        self.offsets.push(self.sites.len());
        Ok(())
    }

    pub fn len(&self) -> usize {
        self.offsets.len() - 1
    }

    pub fn component(&self, index: usize) -> &[usize] {
        &self.sites[self.offsets[index]..self.offsets[index + 1]]
    }
}
