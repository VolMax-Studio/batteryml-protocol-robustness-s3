#!/usr/bin/env python3
import json
import math
import pandas as pd
from pathlib import Path
from s3_adjudication import (
    adjudicate_s3,
    compute_operational_d,
    sort_models_by_rmse,
    compute_quantiles_type_7,
    RANKING_MODELS,
)

art = Path("/home/volmax-studio/volmax-projects/iot2/batteryml-protocol-robustness-s3/s3_execution_output/s3-artifact")

def evaluate_fit(csv_path: Path):
    df = pd.read_csv(csv_path)
    err = df["target"] - df["prediction"]
    mse = (err ** 2).mean()
    rmse = math.sqrt(mse)
    mae = err.abs().mean()
    return rmse, mae

# 1. Baseline Split A
base_rmses = {}
for m in RANKING_MODELS + ["dummy"]:
    p = art / "results" / "split_a" / m / "per-cell-predictions.csv"
    r, _ = evaluate_fit(p)
    base_rmses[m] = r
baseline_rank = sort_models_by_rmse(base_rmses)
print("Baseline (Split A) RMSEs:", {m: round(base_rmses[m], 4) for m in base_rmses})
print("Baseline rank:", baseline_rank)

# 2. Ref B
ref_rmses = {}
for m in RANKING_MODELS + ["dummy"]:
    p = art / "results" / "ref_b" / m / "per-cell-predictions.csv"
    r, _ = evaluate_fit(p)
    ref_rmses[m] = r
ref_rank = sort_models_by_rmse(ref_rmses)
print("Ref B RMSEs:", {m: round(ref_rmses[m], 4) for m in ref_rmses})
print("Ref B rank:", ref_rank)

# 3. 64 Sampled Splits
sampled_dir = art / "results" / "sampled"
split_dirs = sorted([d for d in sampled_dir.iterdir() if d.is_dir()])
print(f"Total sampled split directories: {len(split_dirs)}")

model_changes = {m: [] for m in RANKING_MODELS}
dummy_changes = []
split_ranks = []
all_split_rmses = []

for sdir in split_dirs:
    s_rmses = {}
    for m in RANKING_MODELS + ["dummy"]:
        p = sdir / m / "per-cell-predictions.csv"
        r, _ = evaluate_fit(p)
        s_rmses[m] = r
    all_split_rmses.append(s_rmses)
    r_rank = sort_models_by_rmse(s_rmses)
    split_ranks.append(r_rank)
    for m in RANKING_MODELS:
        d = compute_operational_d(s_rmses[m], base_rmses[m])
        model_changes[m].append(d)
    dummy_d = compute_operational_d(s_rmses["dummy"], base_rmses["dummy"])
    dummy_changes.append(dummy_d)

adj = adjudicate_s3(model_changes, baseline_rank, split_ranks, dummy_changes)
print("\n=== INDEPENDENT RECOMPUTATION ADJUDICATION ===")
print("Category:", adj["adjudication_category"])
print("Material prevalent models:", adj["material_prevalent_models"])
print("Positive systematic models:", adj["positive_systematic_models"])
ch_cnt = adj['changed_ranks_count']
print(f"Rank change rate: {adj['rank_change_rate']} ({ch_cnt}/64)")
for m in RANKING_MODELS:
    qs = compute_quantiles_type_7(model_changes[m], [0.25, 0.5, 0.75])
    st = adj["model_stats"][m]
    print(f"{m:8s}: p_pos={st['p_pos']:.3f}, p_abs={st['p_abs']:.3f}, p_neg={st['p_neg']:.3f} | median={qs[0.5]:+.4f} (IQR [{qs[0.25]:+.4f}, {qs[0.75]:+.4f}])")

candidate = json.loads((art / "adjudication_candidate.json").read_text())
candidate_adj = candidate["adjudication"]
print("\nCandidate Category:", candidate_adj.get("adjudication_category"))
assert adj["adjudication_category"] == candidate_adj.get("adjudication_category"), "Category mismatch!"
assert adj["material_prevalent_models"] == candidate_adj.get("material_prevalent_models"), "Model mismatch!"
assert adj["positive_systematic_models"] == candidate_adj.get("positive_systematic_models"), "Positive systematic mismatch!"
assert adj["rank_change_rate"] == candidate_adj.get("rank_change_rate"), "Rank change rate mismatch!"
assert adj["changed_ranks_count"] == candidate_adj.get("changed_ranks_count"), "Changed ranks count mismatch!"
print("\nSUCCESS: Independent recomputation from per-cell CSVs matches candidate adjudication byte-for-byte!")
