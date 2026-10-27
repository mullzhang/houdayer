//! Store each assignment once, checking full rows even on hash collisions.

use std::collections::{HashMap, hash_map::DefaultHasher};
use std::hash::{Hash, Hasher};

use crate::RunError;

#[derive(Default)]
pub(crate) struct Pool {
    pub rows: Vec<Vec<i8>>,
    buckets: HashMap<u64, Vec<usize>>,
}

impl Pool {
    pub fn insert<E>(&mut self, sample: &[i8]) -> Result<bool, RunError<E>> {
        let mut hasher = DefaultHasher::new();
        sample.hash(&mut hasher);
        self.insert_hashed(sample, hasher.finish())
    }

    fn insert_hashed<E>(&mut self, sample: &[i8], hash: u64) -> Result<bool, RunError<E>> {
        if self
            .buckets
            .get(&hash)
            .is_some_and(|indices| indices.iter().any(|&i| self.rows[i] == sample))
        {
            return Ok(false);
        }
        self.rows.try_reserve(1)?;
        self.buckets.try_reserve(1)?;
        let mut owned = Vec::new();
        owned.try_reserve_exact(sample.len())?;
        owned.extend_from_slice(sample);
        let bucket = self.buckets.entry(hash).or_default();
        bucket.try_reserve(1)?;
        bucket.push(self.rows.len());
        self.rows.push(owned);
        Ok(true)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn collisions_do_not_merge_different_assignments() {
        let mut pool = Pool::default();
        assert!(pool.insert_hashed::<()>(&[-1, 1], 0).unwrap());
        assert!(pool.insert_hashed::<()>(&[1, -1], 0).unwrap());
        assert!(!pool.insert_hashed::<()>(&[-1, 1], 0).unwrap());
        assert_eq!(pool.rows.len(), 2);
    }
}
