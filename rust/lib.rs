//! A deterministic, bounded engine for expanding binary sample pools.

mod cluster;
mod expansion;
mod graph;
mod pool;

#[cfg(feature = "python")]
mod bindings;

pub use expansion::{Config, Output, RunError, Stats, StopReason, expand};
pub use graph::Graph;
