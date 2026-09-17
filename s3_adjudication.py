#!/usr/bin/env python3
"""S3 Adjudication Engine and Estimand Metrics.

Preregistered constants:
- MATERIAL_RELATIVE_CHANGE = 0.10
- NO_SIGNAL_PREVALENCE = 0.20
- MATERIAL_PREVALENCE = 0.50
- SYSTEMATIC_PREVALENCE = 0.80
- NO_MATERIAL_RANK_CHANGE_THRESHOLD = 0.20 (comparator: <)
- ROBUST_RANK_CHANGE_THRESHOLD = 0.80 (comparator: >=)
- ROBUST_MIN_SAME_DIRECTION_MODELS = 2
- MODEL_SPECIFIC_PREVALENT_MODEL_COUNT = 1
- DUMMY_COMPOSITION_PREVALENCE = 0.50
- RANKING_MODELS = ["variance", "ridge", "xgb"]
- RANKING_TIE_BREAK_ORDER = ["variance", "ridge", "xgb"]
"""

from __future__ import annotations

import math
from typing import Any

MATERIAL_RELATIVE_CHANGE = 0.10
NO_SIGNAL_PREVALENCE = 0.20
MATERIAL_PREVALENCE = 0.50
SYSTEMATIC_PREVALENCE = 0.80
NO_MATERIAL_RANK_CHANGE_THRESHOLD = 0.20
ROBUST_RANK_CHANGE_THRESHOLD = 0.80
ROBUST_MIN_SAME_DIRECTION_MODELS = 2
MODEL_SPECIFIC_PREVALENT_MODEL_COUNT = 1
DUMMY_COMPOSITION_PREVALENCE = 0.50

RANKING_MODELS = ["variance", "ridge", "xgb"]
RANKING_TIE_BREAK_ORDER = ["variance", "ridge", "xgb"]


def compute_operational_d(rmse_b: float, rmse_a: float) -> float:
    """Compute relative operational change D = (RMSE_B - RMSE_A) / RMSE_A."""
    if not math.isfinite(rmse_a) or rmse_a <= 0:
        raise ValueError(f"Invalid baseline RMSE_A: {rmse_a}")
    if not math.isfinite(rmse_b):
        raise ValueError(f"Invalid evaluated RMSE_B: {rmse_b}")
    return (rmse_b - rmse_a) / rmse_a


def compute_dummy_skill(rmse_model: float, rmse_dummy: float) -> float:
    """Compute skill relative to dummy: 1 - RMSE(model)/RMSE(dummy)."""
    if not math.isfinite(rmse_dummy) or rmse_dummy <= 0:
        raise ValueError("UNDEFINED_DUMMY_SKILL_DENOMINATOR")
    if not math.isfinite(rmse_model):
        raise ValueError(f"Nonfinite model RMSE: {rmse_model}")
    return 1.0 - (rmse_model / rmse_dummy)


def compute_b2c1_influence(lifted_rmse: float, primary_rmse: float) -> float:
    """Compute b2c1 relative influence J = (lifted - primary) / primary."""
    if not math.isfinite(primary_rmse) or primary_rmse <= 0:
        raise ValueError(f"Invalid primary RMSE: {primary_rmse}")
    if not math.isfinite(lifted_rmse):
        raise ValueError(f"Invalid lifted RMSE: {lifted_rmse}")
    return (lifted_rmse - primary_rmse) / primary_rmse


def sort_models_by_rmse(
    model_rmses: dict[str, float],
    models: list[str] = RANKING_MODELS,
    tie_break_order: list[str] = RANKING_TIE_BREAK_ORDER,
) -> list[str]:
    """Sort models by (raw_rmse, index_in_tie_break_order)."""
    order_idx = {m: i for i, m in enumerate(tie_break_order)}
    return sorted(models, key=lambda m: (model_rmses[m], order_idx[m]))


def check_exact_rmse_ties(
    model_rmses: dict[str, float],
    models: list[str] = RANKING_MODELS,
    tolerance: float = 0.0,
) -> list[tuple[str, str]]:
    """Return pairs of models with exact RMSE tie within tolerance."""
    ties: list[tuple[str, str]] = []
    for i in range(len(models)):
        for j in range(i + 1, len(models)):
            m1, m2 = models[i], models[j]
            if abs(model_rmses[m1] - model_rmses[m2]) <= tolerance:
                ties.append((m1, m2))
    return ties


def compute_quantiles_type_7(values: list[float], qs: list[float]) -> dict[float, float]:
    """Compute sample quantiles according to Hyndman & Fan type 7."""
    if not values:
        raise ValueError("Empty values for quantile computation")
    sorted_v = sorted(values)
    n = len(sorted_v)
    result: dict[float, float] = {}
    for q in qs:
        if not (0.0 <= q <= 1.0):
            raise ValueError(f"Invalid quantile: {q}")
        if n == 1:
            result[q] = sorted_v[0]
            continue
        # Type 7: h = (n - 1) * q + 1 (1-based), so index = (n - 1) * q (0-based)
        h = (n - 1) * q
        floor_h = int(math.floor(h))
        ceil_h = min(floor_h + 1, n - 1)
        frac = h - floor_h
        val = sorted_v[floor_h] + frac * (sorted_v[ceil_h] - sorted_v[floor_h])
        result[q] = val
    return result


def adjudicate_s3(
    model_relative_changes: dict[str, list[float]],
    baseline_rank: list[str],
    split_ranks: list[list[str]],
    dummy_relative_changes: list[float] | None = None,
) -> dict[str, Any]:
    """Execute complete preregistered S3 adjudication logic.
    
    Returns structured adjudication record with exactly one of:
    - NO_MATERIAL_SIGNAL
    - ROBUST_SYSTEMATIC_EFFECT
    - MODEL_SPECIFIC
    - HETEROGENEOUS_SPLIT_DEPENDENT
    """
    k_count = len(split_ranks)
    if k_count == 0:
        raise ValueError("Empty split ranks")

    # 1. Model-level proportions
    model_stats: dict[str, dict[str, Any]] = {}
    material_prevalent_models: list[str] = []
    positive_systematic_models: list[str] = []
    negative_systematic_models: list[str] = []

    for m in RANKING_MODELS:
        changes = model_relative_changes[m]
        if len(changes) != k_count:
            raise ValueError(f"Length mismatch for model {m}: {len(changes)} != {k_count}")

        p_abs = sum(1 for d in changes if abs(d) >= MATERIAL_RELATIVE_CHANGE) / k_count
        p_pos = sum(1 for d in changes if d >= MATERIAL_RELATIVE_CHANGE) / k_count
        p_neg = sum(1 for d in changes if d <= -MATERIAL_RELATIVE_CHANGE) / k_count

        mat_prev = p_abs >= MATERIAL_PREVALENCE
        pos_sys = p_pos >= SYSTEMATIC_PREVALENCE
        neg_sys = p_neg >= SYSTEMATIC_PREVALENCE

        if mat_prev:
            material_prevalent_models.append(m)
        if pos_sys:
            positive_systematic_models.append(m)
        if neg_sys:
            negative_systematic_models.append(m)

        model_stats[m] = {
            "p_abs": p_abs,
            "p_pos": p_pos,
            "p_neg": p_neg,
            "material_prevalent": mat_prev,
            "positive_systematic": pos_sys,
            "negative_systematic": neg_sys,
        }

    # 2. Ranking change rate
    changed_ranks_count = sum(1 for r in split_ranks if r != baseline_rank)
    rank_change_rate = changed_ranks_count / k_count

    # 3. Decision flags
    no_signal_condition = (
        all(model_stats[m]["p_abs"] < NO_SIGNAL_PREVALENCE for m in RANKING_MODELS)
        and (rank_change_rate < NO_MATERIAL_RANK_CHANGE_THRESHOLD)
    )

    same_direction_systematic = (
        len(positive_systematic_models) >= ROBUST_MIN_SAME_DIRECTION_MODELS
        or len(negative_systematic_models) >= ROBUST_MIN_SAME_DIRECTION_MODELS
    )

    systematic_rank = (
        rank_change_rate >= ROBUST_RANK_CHANGE_THRESHOLD
        and len(material_prevalent_models) >= 1
    )

    robust_condition = same_direction_systematic or systematic_rank

    one_model_condition = (
        len(material_prevalent_models) == MODEL_SPECIFIC_PREVALENT_MODEL_COUNT
    )

    # 4. Priority Cascade
    if no_signal_condition:
        category = "NO_MATERIAL_SIGNAL"
    elif robust_condition:
        category = "ROBUST_SYSTEMATIC_EFFECT"
    elif one_model_condition:
        category = "MODEL_SPECIFIC"
    else:
        category = "HETEROGENEOUS_SPLIT_DEPENDENT"

    # 5. Dummy composition sensitivity flag
    dummy_composition_sensitive = False
    dummy_p_abs = None
    if dummy_relative_changes is not None and len(dummy_relative_changes) == k_count:
        dummy_p_abs = sum(1 for d in dummy_relative_changes if abs(d) >= MATERIAL_RELATIVE_CHANGE) / k_count
        dummy_composition_sensitive = dummy_p_abs >= DUMMY_COMPOSITION_PREVALENCE

    return {
        "adjudication_category": category,
        "k_splits": k_count,
        "model_stats": model_stats,
        "rank_change_rate": rank_change_rate,
        "changed_ranks_count": changed_ranks_count,
        "material_prevalent_models": material_prevalent_models,
        "positive_systematic_models": positive_systematic_models,
        "negative_systematic_models": negative_systematic_models,
        "flags": {
            "no_signal": no_signal_condition,
            "robust": robust_condition,
            "same_direction_systematic": same_direction_systematic,
            "systematic_rank": systematic_rank,
            "one_model": one_model_condition,
            "dummy_composition_sensitive": dummy_composition_sensitive,
        },
        "dummy_p_abs": dummy_p_abs,
    }
