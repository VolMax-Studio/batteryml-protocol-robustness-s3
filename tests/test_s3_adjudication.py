#!/usr/bin/env python3
"""Unit and synthetic fuzz tests for S3 adjudication logic."""

import unittest
from s3_adjudication import (
    adjudicate_s3,
    check_exact_rmse_ties,
    compute_b2c1_influence,
    compute_dummy_skill,
    compute_operational_d,
    compute_quantiles_type_7,
    sort_models_by_rmse,
)


class TestS3Adjudication(unittest.TestCase):
    def test_operational_d_and_b2c1(self) -> None:
        d = compute_operational_d(138.50330213051572, 115.78919623655567)
        self.assertAlmostEqual(d, 0.196167748, places=6)
        
        j = compute_b2c1_influence(150.0, 100.0)
        self.assertAlmostEqual(j, 0.50, places=6)

    def test_dummy_skill_and_edge_case(self) -> None:
        skill = compute_dummy_skill(136.0, 400.0)
        self.assertAlmostEqual(skill, 0.66, places=6)
        
        # Zero or nonpositive dummy must raise hard stop
        with self.assertRaises(ValueError):
            compute_dummy_skill(100.0, 0.0)
        with self.assertRaises(ValueError):
            compute_dummy_skill(100.0, -10.0)

    def test_ranking_sort_and_tie_break(self) -> None:
        # distinct
        rmses = {"variance": 133.0, "ridge": 138.0, "xgb": 345.0}
        self.assertEqual(sort_models_by_rmse(rmses), ["variance", "ridge", "xgb"])
        
        # exact tie between variance and ridge: tie break order is [variance, ridge, xgb]
        rmses_tie = {"variance": 135.0, "ridge": 135.0, "xgb": 300.0}
        self.assertEqual(sort_models_by_rmse(rmses_tie), ["variance", "ridge", "xgb"])
        ties = check_exact_rmse_ties(rmses_tie, tolerance=0.0)
        self.assertEqual(len(ties), 1)
        self.assertEqual(ties[0], ("variance", "ridge"))

    def test_quantiles_type_7(self) -> None:
        vals = [10.0, 20.0, 30.0, 40.0, 50.0]
        qs = compute_quantiles_type_7(vals, [0.25, 0.50, 0.75])
        self.assertAlmostEqual(qs[0.50], 30.0, places=6)
        self.assertAlmostEqual(qs[0.25], 20.0, places=6)
        self.assertAlmostEqual(qs[0.75], 40.0, places=6)

    def test_synthetic_fuzz_exhaustive_coverage(self) -> None:
        """Fuzz testing over combinations of model responses to verify all 4 categories are produced."""
        base_rank = ["ridge", "variance", "xgb"]
        rev_rank = ["variance", "ridge", "xgb"]
        k = 20

        categories = set()

        # Scenario 1: NO_SIGNAL
        changes_no_signal = {m: [0.01] * k for m in ["variance", "ridge", "xgb"]}
        ranks_no_signal = [base_rank] * k
        adj_1 = adjudicate_s3(changes_no_signal, base_rank, ranks_no_signal)
        self.assertEqual(adj_1["adjudication_category"], "NO_MATERIAL_SIGNAL")
        categories.add(adj_1["adjudication_category"])

        # Scenario 2: ROBUST (same direction systematic for 2 models)
        changes_robust_1 = {
            "variance": [0.15] * k,  # 100% >= 0.10 -> positive systematic
            "ridge": [0.20] * k,     # 100% >= 0.10 -> positive systematic
            "xgb": [0.0] * k,
        }
        adj_2 = adjudicate_s3(changes_robust_1, base_rank, [base_rank] * k)
        self.assertEqual(adj_2["adjudication_category"], "ROBUST_SYSTEMATIC_EFFECT")
        categories.add(adj_2["adjudication_category"])

        # Scenario 3: ROBUST (systematic rank change >= 80% with >=1 material prevalent model)
        changes_robust_2 = {
            "ridge": [0.15] * 12 + [0.0] * 8, # 60% >= 0.10 -> material prevalent
            "variance": [0.0] * k,
            "xgb": [0.0] * k,
        }
        ranks_robust_2 = [rev_rank] * 18 + [base_rank] * 2 # 90% rank change >= 80%
        adj_3 = adjudicate_s3(changes_robust_2, base_rank, ranks_robust_2)
        self.assertEqual(adj_3["adjudication_category"], "ROBUST_SYSTEMATIC_EFFECT")

        # Scenario 4: MODEL_SPECIFIC (exactly 1 material prevalent model, rank change < 80%)
        changes_one_model = {
            "ridge": [0.15] * 12 + [0.0] * 8, # 60% >= 0.10 -> material prevalent
            "variance": [0.0] * k,
            "xgb": [0.0] * k,
        }
        ranks_one_model = [rev_rank] * 5 + [base_rank] * 15 # 25% rank change
        adj_4 = adjudicate_s3(changes_one_model, base_rank, ranks_one_model)
        self.assertEqual(adj_4["adjudication_category"], "MODEL_SPECIFIC")
        categories.add(adj_4["adjudication_category"])

        # Scenario 5: HETEROGENEOUS_SPLIT_DEPENDENT (e.g. 2 material prevalent models in opposite directions, neither systematic)
        changes_hetero = {
            "ridge": [0.15] * 12 + [0.0] * 8,   # 60% pos -> material prevalent, NOT systematic (needs 80%)
            "variance": [-0.15] * 12 + [0.0] * 8, # 60% neg -> material prevalent, NOT systematic
            "xgb": [0.0] * k,
        }
        ranks_hetero = [rev_rank] * 6 + [base_rank] * 14 # 30% rank change (< 80%)
        adj_5 = adjudicate_s3(changes_hetero, base_rank, ranks_hetero)
        self.assertEqual(adj_5["adjudication_category"], "HETEROGENEOUS_SPLIT_DEPENDENT")
        categories.add(adj_5["adjudication_category"])

        self.assertEqual(
            categories,
            {
                "NO_MATERIAL_SIGNAL",
                "ROBUST_SYSTEMATIC_EFFECT",
                "MODEL_SPECIFIC",
                "HETEROGENEOUS_SPLIT_DEPENDENT",
            },
        )


if __name__ == "__main__":
    unittest.main()
