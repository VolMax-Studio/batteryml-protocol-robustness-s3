#!/usr/bin/env python3
"""Unit tests for S3 deterministic DP sampler and verifier."""

import unittest
from pathlib import Path

from s3_sampler import (
    DERIVED_INTERSECTION,
    EXPECTED_SAMPLER_INPUT_SHA256,
    EXPECTED_SEED_SHA256,
    K,
    MINIMUM_COST_SPLIT_COUNT,
    MINIMUM_MOVES,
    S2_REFERENCE_RANK,
    SEED_TEXT,
    TEST_CELLS,
    TRAIN_CELLS,
    S3Sampler,
)


class TestS3Sampler(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.sampler_input = Path(__file__).resolve().parent.parent / "sampler_input.csv"
        cls.sampler = S3Sampler(cls.sampler_input)

    def test_sampler_input_sha256(self) -> None:
        import hashlib
        digest = hashlib.sha256(self.sampler_input.read_bytes()).hexdigest()
        self.assertEqual(digest, EXPECTED_SAMPLER_INPUT_SHA256)

    def test_dp_total_minimum_cost_count(self) -> None:
        total = self.sampler.total_minimum_cost_splits()
        self.assertEqual(total, MINIMUM_COST_SPLIT_COUNT)
        self.assertEqual(total, 185471)

    def test_seed_derivation_hash(self) -> None:
        import hashlib
        digest = hashlib.sha256(SEED_TEXT.encode("utf-8")).hexdigest()
        self.assertEqual(digest, EXPECTED_SEED_SHA256)

    def test_generated_ranks_count_and_bounds(self) -> None:
        ranks = self.sampler.generate_ranks()
        self.assertEqual(len(ranks), K)
        self.assertEqual(len(ranks), 64)
        
        # Verify no duplicates
        rank_vals = [r for _, _, r in ranks]
        self.assertEqual(len(set(rank_vals)), 64)
        
        # Verify S2 reference rank is strictly excluded
        self.assertNotIn(S2_REFERENCE_RANK, rank_vals)
        
        # Verify all ranks within bounds
        for _, _, r in ranks:
            self.assertGreaterEqual(r, 0)
            self.assertLess(r, MINIMUM_COST_SPLIT_COUNT)

    def test_all_64_split_invariants(self) -> None:
        ranks = self.sampler.generate_ranks()
        for s_idx, _, r in ranks:
            asgn = self.sampler.unrank(r)
            inv = self.sampler.verify_split_invariants(asgn)
            self.assertEqual(inv["train_cells"], TRAIN_CELLS)
            self.assertEqual(inv["test_cells"], TEST_CELLS)
            self.assertEqual(inv["protocol_overlap"], 0)
            self.assertEqual(inv["move_cost"], MINIMUM_MOVES)
            self.assertEqual(inv["intersection_with_a_test"], DERIVED_INTERSECTION)

    def test_manifest_sha256_exact(self) -> None:
        import hashlib
        manifest_path = Path(__file__).resolve().parent.parent / "s3-split-manifest.csv"
        if manifest_path.is_file():
            digest = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
            self.assertEqual(digest, "cf9c269a93053e64ecf9200e0ee704fb0c32d2787f721fc24f0cb711cdc33895")


if __name__ == "__main__":
    unittest.main()
