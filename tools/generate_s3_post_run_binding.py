#!/usr/bin/env python3
"""Generate the S3 post-run binding receipt and governing adjudication.

This tool performs post-run closure for study batteryml-protocol-robustness-s3:
1. Verifies Kaggle API kernel session status and metadata.
2. Binds and verifies the control dataset content byte-for-byte.
3. Collects the complete 264-fit run matrix (Split A, Ref B, 64 sampled splits x 4 models).
4. Independently recomputes RMSE and MAE from raw per-cell predictions.
5. Derives the governing adjudication using frozen s3_adjudication logic.
6. Writes checkpoint manifest, public evidence manifest, and governing receipts.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from s3_adjudication import (
    adjudicate_s3,
    compute_operational_d,
    sort_models_by_rmse,
    compute_quantiles_type_7,
    RANKING_MODELS,
)

INSTANCE = "batteryml-protocol-robustness-s3"
KERNEL_REF = "volmax1/batteryml-protocol-robustness-s3-run"
EXPECTED_KERNEL_ID = 134781615
EXPECTED_CONTROL_DATASET_SLUG = "volmax1/batteryml-protocol-robustness-s3-controls"
EXPECTED_CONTROL_LISTING_SHA256 = "9da5f90c5f4962a873bc49403b1f0a8cb1a20607748386120794bf63f8acd26d"
MODELS = ["variance", "ridge", "xgb", "dummy"]


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text())
    if not isinstance(value, dict):
        raise RuntimeError(f"Expected JSON object: {path}")
    return value


def query_kernel() -> dict[str, Any]:
    # Ensure token is loaded if present in secret file
    token_path = Path("/home/volmax-studio/Documents/Kljucevi/kaggle.txt")
    if token_path.is_file():
        os.environ["KAGGLE_API_TOKEN"] = token_path.read_text().strip()

    try:
        from kaggle.api.kaggle_api_extended import KaggleApi
        from kagglesdk.kernels.types.kernels_api_service import ApiGetKernelRequest
    except ImportError as exc:
        raise RuntimeError("The authenticated Kaggle Python client is required") from exc

    api = KaggleApi()
    api.authenticate()
    status_response = api.kernels_status(KERNEL_REF)
    owner, slug = KERNEL_REF.split("/", 1)
    request = ApiGetKernelRequest()
    request.user_name = owner
    request.kernel_slug = slug
    with api.build_kaggle_client() as client:
        metadata_response = client.kernels.kernels_api_client.get_kernel(request)
    metadata = metadata_response.metadata
    status = str(status_response.status).rsplit(".", 1)[-1]
    observation = {
        "configured_ref": KERNEL_REF,
        "current_version_number": metadata.current_version_number,
        "dataset_data_sources": sorted(metadata.dataset_data_sources or []),
        "docker_image": metadata.docker_image,
        "enable_gpu": metadata.enable_gpu,
        "enable_internet": metadata.enable_internet,
        "kernel_id": metadata.id,
        "last_run_time": str(metadata.last_run_time),
        "status": status,
    }
    if observation["status"] != "COMPLETE":
        raise RuntimeError(f"Kaggle kernel is not COMPLETE: {observation['status']}")
    if EXPECTED_CONTROL_DATASET_SLUG not in observation["dataset_data_sources"]:
        raise RuntimeError(f"Control dataset {EXPECTED_CONTROL_DATASET_SLUG} not in kernel dataset sources")
    return observation


def verify_control_dataset(control_source_dir: Path, runtime_listing_text: str) -> dict[str, Any]:
    files: list[tuple[str, Path]] = []
    for p in control_source_dir.rglob("*"):
        if p.is_file() and p.name != "dataset-metadata.json":
            rel = p.relative_to(control_source_dir).as_posix()
            files.append((rel, p))
    files.sort(key=lambda x: x[0])
    rows = [f"{sha256_file(p)}  {rel}\n" for rel, p in files]
    local_listing = "".join(rows)
    local_hash = sha256_bytes(local_listing.encode())
    runtime_hash = sha256_bytes(runtime_listing_text.encode())

    if local_hash != runtime_hash:
        raise RuntimeError(f"Control dataset listing mismatch: local={local_hash} vs runtime={runtime_hash}")
    if local_hash != EXPECTED_CONTROL_LISTING_SHA256:
        raise RuntimeError(f"Control dataset listing does not match expected: {local_hash} vs {EXPECTED_CONTROL_LISTING_SHA256}")

    return {
        "file_count": len(files),
        "listing_sha256": local_hash,
        "runtime_byte_match": True,
        "source_dir": str(control_source_dir),
    }


def parse_artifact_manifest(path: Path) -> dict[str, str]:
    entries: dict[str, str] = {}
    for line in path.read_text().splitlines():
        digest, separator, relative = line.partition("  ")
        if not separator or len(digest) != 64 or not relative:
            raise RuntimeError(f"Malformed artifact manifest line: {line!r}")
        entries[relative] = digest
    return entries


def write_checkpoint_manifest(artifact: Path, entries: dict[str, str]) -> Path:
    output = artifact / "checkpoint-files.sha256"
    rows = [f"{digest}  {relative}\n" for relative, digest in sorted(entries.items()) if relative.endswith(".ckpt")]
    if len(rows) != 264:
        raise RuntimeError(f"Expected 264 checkpoints in artifact manifest, found {len(rows)}")
    for row in rows:
        digest, _, relative = row.rstrip("\n").partition("  ")
        checkpoint = artifact / relative
        if not checkpoint.is_file() or sha256_file(checkpoint) != digest:
            raise RuntimeError(f"Checkpoint does not match frozen artifact manifest: {checkpoint}")
    output.write_text("".join(rows))
    return output


def write_public_manifest(output_root: Path) -> Path:
    output = output_root / "public-evidence-files.sha256"
    excluded = {
        output,
        output_root / "post-run-binding-receipt.json",
        output_root / "governing-adjudication.json",
    }
    rows: list[str] = []
    for path in sorted(output_root.rglob("*"), key=lambda item: item.relative_to(output_root).as_posix()):
        if not path.is_file() or path in excluded:
            continue
        relative = path.relative_to(output_root).as_posix()
        # Exclude bulky raw cache files, installed site-packages, logs, and checkpoints from public repo manifest
        if (
            relative.startswith("s3-processed-matr/")
            or relative.startswith("s3-site-packages/")
            or relative.endswith(".ckpt")
            or relative.endswith(".log")
        ):
            continue
        rows.append(f"{sha256_file(path)}  {relative}\n")
    output.write_text("".join(rows))
    return output


def evaluate_predictions(csv_path: Path) -> tuple[float, float, int]:
    df = pd.read_csv(csv_path)
    err = df["target"] - df["prediction"]
    mse = float((err ** 2).mean())
    rmse = float(math.sqrt(mse))
    mae = float(err.abs().mean())
    return rmse, mae, len(df)


def collect_run_matrix(artifact: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    runs: list[dict[str, Any]] = []

    # 1. Baseline Split A
    base_rmses: dict[str, float] = {}
    for model in MODELS:
        dir_path = artifact / "results" / "split_a" / model
        pred_path = dir_path / "per-cell-predictions.csv"
        receipt_path = dir_path / "run-receipt.json"
        param_path = dir_path / "resolved-model-parameters.json"
        ckpt_path = dir_path / "latest.ckpt"
        b2c1_path = dir_path / "b2c1-prediction.json"

        for p in (pred_path, receipt_path, param_path, ckpt_path, b2c1_path):
            if not p.is_file():
                raise RuntimeError(f"Missing run file: {p}")

        rcpt = load_object(receipt_path)
        recomp_rmse, recomp_mae, n_test = evaluate_predictions(pred_path)
        if not math.isclose(recomp_rmse, rcpt["rmse"], rel_tol=1e-4, abs_tol=1e-4):
            raise RuntimeError(f"RMSE mismatch in Split A {model}: {recomp_rmse} vs {rcpt['rmse']}")

        base_rmses[model] = recomp_rmse
        runs.append({
            "split_type": "split_a",
            "draw_index": None,
            "split_rank": None,
            "execution_position": None,
            "model": model,
            "rmse": rcpt["rmse"],
            "mae": rcpt["mae"],
            "recomputed_rmse": recomp_rmse,
            "recomputed_mae": recomp_mae,
            "test_count": n_test,
            "predictions_sha256": sha256_file(pred_path),
            "run_receipt_sha256": sha256_file(receipt_path),
            "parameters_sha256": sha256_file(param_path),
            "checkpoint_sha256": sha256_file(ckpt_path),
            "b2c1_prediction_sha256": sha256_file(b2c1_path),
        })

    baseline_rank = sort_models_by_rmse(base_rmses)

    # 2. Ref B
    ref_rmses: dict[str, float] = {}
    for model in MODELS:
        dir_path = artifact / "results" / "ref_b" / model
        pred_path = dir_path / "per-cell-predictions.csv"
        receipt_path = dir_path / "run-receipt.json"
        param_path = dir_path / "resolved-model-parameters.json"
        ckpt_path = dir_path / "latest.ckpt"
        b2c1_path = dir_path / "b2c1-prediction.json"

        for p in (pred_path, receipt_path, param_path, ckpt_path, b2c1_path):
            if not p.is_file():
                raise RuntimeError(f"Missing run file: {p}")

        rcpt = load_object(receipt_path)
        recomp_rmse, recomp_mae, n_test = evaluate_predictions(pred_path)
        if not math.isclose(recomp_rmse, rcpt["rmse"], rel_tol=1e-4, abs_tol=1e-4):
            raise RuntimeError(f"RMSE mismatch in Ref B {model}: {recomp_rmse} vs {rcpt['rmse']}")

        ref_rmses[model] = recomp_rmse
        runs.append({
            "split_type": "ref_b",
            "draw_index": None,
            "split_rank": None,
            "execution_position": None,
            "model": model,
            "rmse": rcpt["rmse"],
            "mae": rcpt["mae"],
            "recomputed_rmse": recomp_rmse,
            "recomputed_mae": recomp_mae,
            "test_count": n_test,
            "predictions_sha256": sha256_file(pred_path),
            "run_receipt_sha256": sha256_file(receipt_path),
            "parameters_sha256": sha256_file(param_path),
            "checkpoint_sha256": sha256_file(ckpt_path),
            "b2c1_prediction_sha256": sha256_file(b2c1_path),
        })

    # 3. 64 Sampled Splits
    sampled_dir = artifact / "results" / "sampled"
    split_dirs = sorted([d for d in sampled_dir.iterdir() if d.is_dir()])
    if len(split_dirs) != 64:
        raise RuntimeError(f"Expected 64 sampled split directories, found {len(split_dirs)}")

    model_changes: dict[str, list[float]] = {m: [] for m in RANKING_MODELS}
    dummy_changes: list[float] = []
    split_ranks: list[list[str]] = []

    for sdir in split_dirs:
        s_rmses: dict[str, float] = {}
        for model in MODELS:
            pred_path = sdir / model / "per-cell-predictions.csv"
            receipt_path = sdir / model / "run-receipt.json"
            param_path = sdir / model / "resolved-model-parameters.json"
            ckpt_path = sdir / model / "latest.ckpt"
            b2c1_path = sdir / model / "b2c1-prediction.json"

            for p in (pred_path, receipt_path, param_path, ckpt_path, b2c1_path):
                if not p.is_file():
                    raise RuntimeError(f"Missing run file: {p}")

            rcpt = load_object(receipt_path)
            recomp_rmse, recomp_mae, n_test = evaluate_predictions(pred_path)
            if not math.isclose(recomp_rmse, rcpt["rmse"], rel_tol=1e-4, abs_tol=1e-4):
                raise RuntimeError(f"RMSE mismatch in {sdir.name} {model}: {recomp_rmse} vs {rcpt['rmse']}")

            s_rmses[model] = recomp_rmse
            runs.append({
                "split_type": "sampled",
                "directory": sdir.name,
                "draw_index": rcpt["draw_index"],
                "split_rank": rcpt["split_rank"],
                "execution_position": rcpt["execution_position"],
                "model": model,
                "rmse": rcpt["rmse"],
                "mae": rcpt["mae"],
                "recomputed_rmse": recomp_rmse,
                "recomputed_mae": recomp_mae,
                "test_count": n_test,
                "predictions_sha256": sha256_file(pred_path),
                "run_receipt_sha256": sha256_file(receipt_path),
                "parameters_sha256": sha256_file(param_path),
                "checkpoint_sha256": sha256_file(ckpt_path),
                "b2c1_prediction_sha256": sha256_file(b2c1_path),
            })

        s_rank = sort_models_by_rmse(s_rmses)
        split_ranks.append(s_rank)
        for m in RANKING_MODELS:
            d = compute_operational_d(s_rmses[m], base_rmses[m])
            model_changes[m].append(d)
        dummy_d = compute_operational_d(s_rmses["dummy"], base_rmses["dummy"])
        dummy_changes.append(dummy_d)

    if len(runs) != 264:
        raise RuntimeError(f"Expected 264 total runs, found {len(runs)}")

    adjudication = adjudicate_s3(model_changes, baseline_rank, split_ranks, dummy_changes)

    # Add quantiles and summary details
    quantiles: dict[str, dict[str, float]] = {}
    for m in RANKING_MODELS:
        qs = compute_quantiles_type_7(model_changes[m], [0.10, 0.25, 0.50, 0.75, 0.90])
        quantiles[m] = {f"q_{int(k*100):02d}": v for k, v in qs.items()}

    dummy_qs = compute_quantiles_type_7(dummy_changes, [0.10, 0.25, 0.50, 0.75, 0.90])
    dummy_quantiles = {f"q_{int(k*100):02d}": v for k, v in dummy_qs.items()}

    recomputed_summary = {
        "adjudication": adjudication,
        "baseline_rank": baseline_rank,
        "baseline_rmses": base_rmses,
        "d_rmse_quantiles": quantiles,
        "dummy_d_quantiles": dummy_quantiles,
        "ref_b_rank": sort_models_by_rmse(ref_rmses),
        "ref_b_rmses": ref_rmses,
    }

    return runs, recomputed_summary


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--control-source-dir", type=Path, required=True)
    parser.add_argument("--receipt", type=Path)
    parser.add_argument("--adjudication-out", type=Path)
    args = parser.parse_args()

    output_root = args.output_root.resolve()
    artifact = output_root / "s3-artifact"
    report_path = output_root / "EXECUTION_REPORT.json"
    listing_path = output_root / "control-dataset-files.sha256"
    ledger_path = artifact / "attempt-ledger.json"
    closure_path = artifact / "execution-closure.json"
    completion_path = artifact / "completion-receipt.json"
    artifact_manifest_path = artifact / "artifact-files.sha256"
    candidate_adj_path = artifact / "adjudication_candidate.json"
    receipt_path = (args.receipt or output_root / "post-run-binding-receipt.json").resolve()
    adj_out_path = (args.adjudication_out or output_root / "governing-adjudication.json").resolve()

    report = load_object(report_path)
    ledger = load_object(ledger_path)
    closure = load_object(closure_path)
    completion = load_object(completion_path)
    candidate_adj = load_object(candidate_adj_path)

    if closure.get("ratification", {}).get("instance") != INSTANCE:
        raise RuntimeError("Execution closure instance mismatch")
    if not report.get("scientific_run_executed") or report.get("exit_code") != 0:
        raise RuntimeError("Execution report does not describe a successful scientific run")

    runtime_listing = listing_path.read_text()
    runtime_listing_sha = sha256_bytes(runtime_listing.encode())
    if runtime_listing_sha != report.get("control_dataset_listing_sha256"):
        raise RuntimeError("Runtime listing SHA-256 differs from EXECUTION_REPORT.json")

    control_binding = verify_control_dataset(args.control_source_dir.resolve(), runtime_listing)
    artifact_entries = parse_artifact_manifest(artifact_manifest_path)
    checkpoint_manifest = write_checkpoint_manifest(artifact, artifact_entries)
    runs, recomputed_summary = collect_run_matrix(artifact)
    public_manifest = write_public_manifest(output_root)
    kernel = query_kernel()

    # Verify that independent recomputation matches candidate adjudication
    recomp_adj = recomputed_summary["adjudication"]
    cand_adj = candidate_adj["adjudication"]
    if recomp_adj["adjudication_category"] != cand_adj["adjudication_category"]:
        raise RuntimeError(f"Adjudication category mismatch: {recomp_adj['adjudication_category']} vs {cand_adj['adjudication_category']}")
    if recomp_adj["material_prevalent_models"] != cand_adj["material_prevalent_models"]:
        raise RuntimeError(f"Material prevalent models mismatch: {recomp_adj['material_prevalent_models']} vs {cand_adj['material_prevalent_models']}")

    output_hashes = {
        "artifact_manifest_sha256": sha256_file(artifact_manifest_path),
        "attempt_ledger_sha256": sha256_file(ledger_path),
        "candidate_adjudication_sha256": sha256_file(candidate_adj_path),
        "checkpoint_manifest_sha256": sha256_file(checkpoint_manifest),
        "completion_receipt_sha256": sha256_file(completion_path),
        "control_dataset_files_listing_sha256": runtime_listing_sha,
        "execution_closure_sha256": sha256_file(closure_path),
        "execution_report_sha256": sha256_file(report_path),
        "gate_1_receipt_sha256": sha256_file(artifact / "gate-1-positive-control-a.json"),
        "gate_2_receipt_sha256": sha256_file(artifact / "gate-2-reference-split-b.json"),
        "public_evidence_manifest_sha256": sha256_file(public_manifest),
    }

    governing_hashes = {
        **report["governing"],
        "driver_sha256": closure["ratification"]["driver_sha256"],
        "governing_scientific_commit": closure["ratification"]["governing_scientific_commit"],
        "implementation_commit": closure["ratification"]["implementation_commit"],
        "membership_commitment_sha256": closure["ratification"]["membership_commitment_sha256"],
        "ratification_receipt_sha256": report["ratification_receipt_sha256"],
        "runner_sha256": report["runner_sha256"],
    }

    governing_adjudication_record = {
        "adjudication": recomp_adj,
        "baseline_rank": recomputed_summary["baseline_rank"],
        "baseline_rmses": recomputed_summary["baseline_rmses"],
        "d_rmse_quantiles": recomputed_summary["d_rmse_quantiles"],
        "dummy_d_quantiles": recomputed_summary["dummy_d_quantiles"],
        "governing_commit": closure["ratification"]["governing_scientific_commit"],
        "instance": INSTANCE,
        "ref_b_rank": recomputed_summary["ref_b_rank"],
        "ref_b_rmses": recomputed_summary["ref_b_rmses"],
        "status": "GOVERNING_RATIFIED_ADJUDICATION",
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
    }
    adj_out_path.write_text(json.dumps(governing_adjudication_record, indent=2, sort_keys=True) + "\n")

    receipt = {
        "adjudication_summary": {
            "adjudication_category": recomp_adj["adjudication_category"],
            "attempt": ledger["attempt_number"],
            "disposition": ledger["disposition"],
            "material_prevalent_models": recomp_adj["material_prevalent_models"],
            "positive_systematic_models": recomp_adj["positive_systematic_models"],
            "rank_change_rate": recomp_adj["rank_change_rate"],
            "changed_ranks_count": recomp_adj["changed_ranks_count"],
            "quantiles": recomputed_summary["d_rmse_quantiles"],
        },
        "closure_step_scientific_run_executed": False,
        "control_dataset_binding": {
            "configured_slug": EXPECTED_CONTROL_DATASET_SLUG,
            "runtime_file_count": control_binding["file_count"],
            "runtime_listing_sha256": runtime_listing_sha,
            "runtime_byte_match": True,
        },
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "generator_sha256": sha256_file(Path(__file__).resolve()),
        "governing_adjudication_sha256": sha256_file(adj_out_path),
        "governing_hashes": governing_hashes,
        "kernel_binding": kernel,
        "output_file_hashes": output_hashes,
        "run_matrix_count": len(runs),
        "scientific_run_executed_in_bound_attempt": True,
        "status": "POST_RUN_BINDING_COMPLETE_GENERATED",
        "study_instance": INSTANCE,
    }
    receipt_path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")

    print(json.dumps({
        "status": "SUCCESS",
        "adjudication": recomp_adj["adjudication_category"],
        "receipt": str(receipt_path),
        "receipt_sha256": sha256_file(receipt_path),
        "governing_adjudication": str(adj_out_path),
        "governing_adjudication_sha256": sha256_file(adj_out_path),
        "run_matrix_count": len(runs),
    }, indent=2, sort_keys=True))


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise
