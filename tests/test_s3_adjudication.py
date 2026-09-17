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

    def test_threshold_equality_boundaries(self) -> None:
        """Verify strict inequality vs equality at all boundary thresholds."""
        base_rank = ["ridge", "variance", "xgb"]
        rev_rank = ["variance", "ridge", "xgb"]
        k = 100

        # 1. Delta boundary: |D| >= 0.10, D >= 0.10, D <= -0.10
        # Exactly 0.10 must count as material and positive
        ch_pos_boundary = {"variance": [0.10] * k, "ridge": [0.0] * k, "xgb": [0.0] * k}
        adj_b1 = adjudicate_s3(ch_pos_boundary, base_rank, [base_rank] * k)
        self.assertEqual(adj_b1["model_stats"]["variance"]["p_abs"], 1.0)
        self.assertEqual(adj_b1["model_stats"]["variance"]["p_pos"], 1.0)
        self.assertTrue(adj_b1["model_stats"]["variance"]["material_prevalent"])
        self.assertTrue(adj_b1["model_stats"]["variance"]["positive_systematic"])

        # Exactly -0.10 must count as material and negative
        ch_neg_boundary = {"variance": [-0.10] * k, "ridge": [0.0] * k, "xgb": [0.0] * k}
        adj_b2 = adjudicate_s3(ch_neg_boundary, base_rank, [base_rank] * k)
        self.assertEqual(adj_b2["model_stats"]["variance"]["p_abs"], 1.0)
        self.assertEqual(adj_b2["model_stats"]["variance"]["p_neg"], 1.0)
        self.assertTrue(adj_b2["model_stats"]["variance"]["negative_systematic"])

        # 0.099999 must NOT count
        ch_sub_boundary = {"variance": [0.099999] * k, "ridge": [0.0] * k, "xgb": [0.0] * k}
        adj_b3 = adjudicate_s3(ch_sub_boundary, base_rank, [base_rank] * k)
        self.assertEqual(adj_b3["model_stats"]["variance"]["p_abs"], 0.0)
        self.assertEqual(adj_b3["adjudication_category"], "NO_MATERIAL_SIGNAL")

        # 2. NO_SIGNAL threshold: p_abs < 0.20 and rank_change < 0.20
        # Exactly 19/100 (0.19) is NO_SIGNAL
        ch_19 = {"variance": [0.15] * 19 + [0.0] * 81, "ridge": [0.0] * k, "xgb": [0.0] * k}
        adj_19 = adjudicate_s3(ch_19, base_rank, [rev_rank] * 19 + [base_rank] * 81)
        self.assertEqual(adj_19["adjudication_category"], "NO_MATERIAL_SIGNAL")

        # Exactly 20/100 (0.20) breaks NO_SIGNAL (p_abs < 0.20 is false)
        ch_20 = {"variance": [0.15] * 20 + [0.0] * 80, "ridge": [0.0] * k, "xgb": [0.0] * k}
        adj_20 = adjudicate_s3(ch_20, base_rank, [base_rank] * k)
        self.assertNotEqual(adj_20["adjudication_category"], "NO_MATERIAL_SIGNAL")
        self.assertEqual(adj_20["adjudication_category"], "HETEROGENEOUS_SPLIT_DEPENDENT")

        # Exactly 20/100 rank change breaks NO_SIGNAL
        ch_0 = {"variance": [0.0] * k, "ridge": [0.0] * k, "xgb": [0.0] * k}
        adj_rk20 = adjudicate_s3(ch_0, base_rank, [rev_rank] * 20 + [base_rank] * 80)
        self.assertNotEqual(adj_rk20["adjudication_category"], "NO_MATERIAL_SIGNAL")
        self.assertEqual(adj_rk20["adjudication_category"], "HETEROGENEOUS_SPLIT_DEPENDENT")

        # 3. Material prevalence threshold: p_abs >= 0.50
        # Exactly 49/100 is NOT material prevalent
        ch_49 = {"variance": [0.15] * 49 + [0.0] * 51, "ridge": [0.0] * k, "xgb": [0.0] * k}
        adj_49 = adjudicate_s3(ch_49, base_rank, [base_rank] * k)
        self.assertFalse(adj_49["model_stats"]["variance"]["material_prevalent"])

        # Exactly 50/100 IS material prevalent
        ch_50 = {"variance": [0.15] * 50 + [0.0] * 50, "ridge": [0.0] * k, "xgb": [0.0] * k}
        adj_50 = adjudicate_s3(ch_50, base_rank, [base_rank] * k)
        self.assertTrue(adj_50["model_stats"]["variance"]["material_prevalent"])
        self.assertEqual(adj_50["adjudication_category"], "MODEL_SPECIFIC")

        # 4. Systematic threshold: p_pos >= 0.80 and p_neg >= 0.80
        # Exactly 79/100 is NOT systematic
        ch_79 = {"variance": [0.15] * 79 + [0.0] * 21, "ridge": [0.15] * 79 + [0.0] * 21, "xgb": [0.0] * k}
        adj_79 = adjudicate_s3(ch_79, base_rank, [base_rank] * k)
        self.assertFalse(adj_79["model_stats"]["variance"]["positive_systematic"])
        self.assertEqual(adj_79["adjudication_category"], "HETEROGENEOUS_SPLIT_DEPENDENT")

        # Exactly 80/100 IS systematic (2 models -> ROBUST)
        ch_80 = {"variance": [0.15] * 80 + [0.0] * 20, "ridge": [0.15] * 80 + [0.0] * 20, "xgb": [0.0] * k}
        adj_80 = adjudicate_s3(ch_80, base_rank, [base_rank] * k)
        self.assertTrue(adj_80["model_stats"]["variance"]["positive_systematic"])
        self.assertTrue(adj_80["model_stats"]["ridge"]["positive_systematic"])
        self.assertEqual(adj_80["adjudication_category"], "ROBUST_SYSTEMATIC_EFFECT")

    def test_negative_systematic_robust_branch(self) -> None:
        """Verify that negative-systematic models trigger ROBUST, and mixed signs do not combine."""
        base_rank = ["ridge", "variance", "xgb"]
        k = 50

        # 2 models negative systematic -> ROBUST
        ch_neg2 = {
            "variance": [-0.20] * 40 + [0.0] * 10,  # 80% negative
            "ridge": [-0.15] * 42 + [0.0] * 8,     # 84% negative
            "xgb": [0.0] * k,
        }
        adj_neg2 = adjudicate_s3(ch_neg2, base_rank, [base_rank] * k)
        self.assertEqual(adj_neg2["adjudication_category"], "ROBUST_SYSTEMATIC_EFFECT")
        self.assertTrue(adj_neg2["flags"]["same_direction_systematic"])

        # 3 models negative systematic -> ROBUST
        ch_neg3 = {
            "variance": [-0.20] * k,
            "ridge": [-0.15] * k,
            "xgb": [-0.30] * k,
        }
        adj_neg3 = adjudicate_s3(ch_neg3, base_rank, [base_rank] * k)
        self.assertEqual(adj_neg3["adjudication_category"], "ROBUST_SYSTEMATIC_EFFECT")

        # 1 positive systematic + 1 negative systematic: NOT same-direction systematic!
        ch_mixed = {
            "variance": [0.20] * 40 + [0.0] * 10,  # 80% positive systematic
            "ridge": [-0.20] * 40 + [0.0] * 10,   # 80% negative systematic
            "xgb": [0.0] * k,
        }
        adj_mixed = adjudicate_s3(ch_mixed, base_rank, [base_rank] * k)
        self.assertFalse(adj_mixed["flags"]["same_direction_systematic"])
        # Both are material prevalent (2 models), rank change = 0 -> HETEROGENEOUS
        self.assertEqual(adj_mixed["adjudication_category"], "HETEROGENEOUS_SPLIT_DEPENDENT")

    def test_priority_cascade_precedence(self) -> None:
        """Verify strict priority cascade ordering."""
        base_rank = ["ridge", "variance", "xgb"]
        rev_rank = ["variance", "ridge", "xgb"]
        k = 20

        # Priority 2 (ROBUST via systematic rank) over Priority 3 (MODEL_SPECIFIC):
        # 1 model material prevalent (would satisfy MODEL_SPECIFIC),
        # but rank change is >= 80% (satisfies systematic_rank in ROBUST).
        # Priority 2 MUST govern.
        ch_p2_over_p3 = {
            "ridge": [0.20] * 12 + [0.0] * 8, # 60% material prevalent
            "variance": [0.0] * k,
            "xgb": [0.0] * k,
        }
        ranks_p2_over_p3 = [rev_rank] * 16 + [base_rank] * 4 # 80% rank change
        adj = adjudicate_s3(ch_p2_over_p3, base_rank, ranks_p2_over_p3)
        self.assertEqual(adj["adjudication_category"], "ROBUST_SYSTEMATIC_EFFECT")

    def test_exhaustive_truth_table_combinatorial_fuzz(self) -> None:
        """Exhaustive truth-table fuzz across 5,103 combinations with an independent formal oracle."""
        base_rank = ["ridge", "variance", "xgb"]
        rev_rank = ["variance", "ridge", "xgb"]
        k = 100

        # Model state generator: returns (list of deltas for 100 splits, p_abs, p_pos, p_neg)
        model_states = [
            ("ZERO", [0.0] * 100, 0.0, 0.0, 0.0),
            ("SUB_NO_SIG", [0.15] * 19 + [0.0] * 81, 0.19, 0.19, 0.0),
            ("AT_NO_SIG", [0.15] * 20 + [0.0] * 80, 0.20, 0.20, 0.0),
            ("INTER_POS", [0.15] * 40 + [0.0] * 60, 0.40, 0.40, 0.0),
            ("MAT_POS", [0.15] * 50 + [0.0] * 50, 0.50, 0.50, 0.0),
            ("MAT_NEG", [-0.15] * 50 + [0.0] * 50, 0.50, 0.0, 0.50),
            ("SYS_POS", [0.15] * 80 + [0.0] * 20, 0.80, 0.80, 0.0),
            ("SYS_NEG", [-0.15] * 80 + [0.0] * 20, 0.80, 0.0, 0.80),
            ("ALL_POS", [0.15] * 100, 1.0, 1.0, 0.0),
        ]

        rank_change_cases = [
            (0, 0.0),
            (19, 0.19),
            (20, 0.20),
            (50, 0.50),
            (79, 0.79),
            (80, 0.80),
            (100, 1.0),
        ]

        def formal_oracle(p_abs: dict[str, float], p_pos: dict[str, float], p_neg: dict[str, float], rk_rate: float) -> str:
            # Predicate 1: NO_SIGNAL
            no_sig = all(p_abs[m] < 0.20 for m in ["variance", "ridge", "xgb"]) and (rk_rate < 0.20)
            if no_sig:
                return "NO_MATERIAL_SIGNAL"

            # Predicate 2: ROBUST
            pos_sys = sum(1 for m in ["variance", "ridge", "xgb"] if p_pos[m] >= 0.80)
            neg_sys = sum(1 for m in ["variance", "ridge", "xgb"] if p_neg[m] >= 0.80)
            same_dir = (pos_sys >= 2) or (neg_sys >= 2)
            mat_prev = sum(1 for m in ["variance", "ridge", "xgb"] if p_abs[m] >= 0.50)
            sys_rank = (rk_rate >= 0.80) and (mat_prev >= 1)
            if same_dir or sys_rank:
                return "ROBUST_SYSTEMATIC_EFFECT"

            # Predicate 3: MODEL_SPECIFIC
            if mat_prev == 1:
                return "MODEL_SPECIFIC"

            # Predicate 4: HETEROGENEOUS
            return "HETEROGENEOUS_SPLIT_DEPENDENT"

        category_counts = {
            "NO_MATERIAL_SIGNAL": 0,
            "ROBUST_SYSTEMATIC_EFFECT": 0,
            "MODEL_SPECIFIC": 0,
            "HETEROGENEOUS_SPLIT_DEPENDENT": 0,
        }

        total_tested = 0
        for name_v, deltas_v, p_abs_v, p_pos_v, p_neg_v in model_states:
            for name_r, deltas_r, p_abs_r, p_pos_r, p_neg_r in model_states:
                for name_x, deltas_x, p_abs_x, p_pos_x, p_neg_x in model_states:
                    changes = {
                        "variance": deltas_v,
                        "ridge": deltas_r,
                        "xgb": deltas_x,
                    }
                    p_abs_map = {"variance": p_abs_v, "ridge": p_abs_r, "xgb": p_abs_x}
                    p_pos_map = {"variance": p_pos_v, "ridge": p_pos_r, "xgb": p_pos_x}
                    p_neg_map = {"variance": p_neg_v, "ridge": p_neg_r, "xgb": p_neg_x}

                    for changed_rk_count, rk_rate in rank_change_cases:
                        ranks = [rev_rank] * changed_rk_count + [base_rank] * (k - changed_rk_count)
                        expected_cat = formal_oracle(p_abs_map, p_pos_map, p_neg_map, rk_rate)

                        adj = adjudicate_s3(changes, base_rank, ranks)
                        actual_cat = adj["adjudication_category"]

                        self.assertEqual(
                            actual_cat,
                            expected_cat,
                            f"Mismatch on state ({name_v}, {name_r}, {name_x}, rk_rate={rk_rate}): "
                            f"expected {expected_cat}, got {actual_cat}",
                        )
                        category_counts[actual_cat] += 1
                        total_tested += 1

        self.assertEqual(total_tested, 9 * 9 * 9 * 7)  # 5,103 combinations
        # Verify that all 4 categories were encountered and verified
        for cat, cnt in category_counts.items():
            self.assertGreater(cnt, 0, f"Category {cat} was never triggered in fuzz testing")


if __name__ == "__main__":
    unittest.main()
