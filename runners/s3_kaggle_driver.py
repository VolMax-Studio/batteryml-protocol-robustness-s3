#!/usr/bin/env python3
"""Fail-closed scientific driver for BatteryML Protocol Robustness S3 on Kaggle.

Executes K=64 exact-size minimum-cost protocol-disjoint splits with:
- Preflight governing verification (DP count, ref rank, rank hashes, membership commitment, manifest SHA)
- Input hash verification and BatteryML source verification
- Isolated preprocessing into s3-processed-matr
- Positive Control Gate 1 (Split A): 4 models (dummy, variance, ridge, xgb), tolerance <= 1.0%
- Positive Control Gate 2 (S2.1 Reference Split B): 4 models, tolerance <= 1.0%
- 256 Sampled Model Fits (64 splits x 4 models in ascending split_rank order)
- Outlier evaluation on b2c1 without model refitting (verified byte-identical primary predictions and checkpoint)
- Hard stop on B2C1_LIFT_INVALID
- Paired diagnostic P_mk on 32-cell intersection
- Cell-level Top-3 SSE concentration
- Protocol-level Top-1 concentration
- Dummy composition control & relative skill
- Blindness protection: NO scientific metrics printed to stdout
- Produces adjudication_candidate.json (governing adjudication produced post-binding)
- Fail-closed exception handling and attempt ledger management
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
import platform
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np


INSTANCE = "batteryml-protocol-robustness-s3"
GOVERNING_FROZEN_COMMIT = "0958e89a0e994ed9923da26e04e1f4bfb956ab7f"

INPUT = Path(os.environ.get(
    "S3_INPUT_ROOT",
    "/kaggle/input/datasets/volmax1/batteryml-protocol-robustness-s3-controls",
))
RAW = Path(os.environ.get(
    "S3_RAW_ROOT",
    "/kaggle/input/datasets/rickandjoe/mit-battery-degradation-dataset",
))
WORKING = Path(os.environ.get("S3_WORKING_ROOT", "/kaggle/working"))

REPO = INPUT / "BatteryML"
SPLIT_MANIFEST = INPUT / "s3-split-manifest.csv"
MEMBERSHIP_COMMITMENT = INPUT / "s3-test-membership-commitment.csv"
SAMPLER_INPUT = INPUT / "sampler_input.csv"
SAMPLER_RANKS = INPUT / "s3-sampler-ranks.json"
SOURCE_MANIFEST = INPUT / "batteryml-source-files.sha256"
PREREGISTRATION = INPUT / "PREREGISTRATION.md"
WHEELS = INPUT / "offline-wheels"

PROCESSED = WORKING / "s3-processed-matr"
SITE = WORKING / "s3-site-packages"
ARTIFACT = WORKING / "s3-artifact"
DRIVER = Path(__file__).resolve()

# Expected Hashes & Commitments
EXPECTED_PREREG_SHA = "5c39c1a31fd67299f62828f2ab0b48e982f159b74532ae7b29140ff96fce1350"
EXPECTED_SPLIT_MANIFEST_SHA = "cf9c269a93053e64ecf9200e0ee704fb0c32d2787f721fc24f0cb711cdc33895"
EXPECTED_MEMBERSHIP_COMMITMENT_SHA = "53a157ecd49c0a238cd5028c6ab840431a7ecb600b067290ee51645820cb5ada"
EXPECTED_SAMPLER_INPUT_SHA = "ac672728d9857c417d4f51812f31b20711307f0e7ee20efacf8f38f1b3dfb42e"
EXPECTED_SAMPLER_RANKS_SHA = "43ae754eabe156f000f1929e5a12c1aa89f889b0fe31c774a330bac39cc200ae"
EXPECTED_SOURCE_MANIFEST_SHA = "5e239025955a160586a666b3cd50deb03c0e60e8ccf316fbb111156f197a516e"
EXPECTED_BASE_FREEZE_SHA = "e137b12924bbb4fbb83f45c8ccb3419ba4e5556d01d977a05a7ab4e175155c35"

EXPECTED_DRAW_ORDER_HASH = "1d84b7bf864945a26ec0a5d2feec754b6ed6b4bf50b9f4e5b02bc45720b0ff02"
EXPECTED_ASCENDING_HASH = "0f2de17c98e615023ef5966630fd93962382c4566c36a43b0d386bd0a8dbfc40"
EXPECTED_DP_COUNT = 185471
EXPECTED_S2_REF_RANK = 169301

MIN_RAM_BYTES = 31 * 1024**3
EXACT_CPUS = 4

CONTROL_GATE_REL_TOLERANCE = 0.010

S2_1_A_REFERENCE_RMSE = {
    "variance": 136.12960815429688,
    "ridge": 115.78919623655567,
    "xgb": 333.66455078125,
}
S2_1_A_REFERENCE_MAE = {
    "variance": 109.06492614746094,
    "ridge": 80.41317415887194,
    "xgb": 155.50146484375,
}

S2_1_B_REFERENCE_RMSE = {
    "variance": 133.47593688964844,
    "ridge": 138.50330213051572,
    "xgb": 345.9460754394531,
}
S2_1_B_REFERENCE_MAE = {
    "variance": 109.73089599609375,
    "ridge": 83.30479497681773,
    "xgb": 212.07666015625,
}

MODELS = {
    "dummy": REPO / "configs/baselines/sklearn/dummy/matr_1.yaml",
    "variance": REPO / "configs/baselines/sklearn/variance_model/matr_1.yaml",
    "ridge": REPO / "configs/baselines/sklearn/ridge/matr_1.yaml",
    "xgb": REPO / "configs/baselines/sklearn/xgb/matr_1.yaml",
}
ORDERED_MODELS = ["dummy", "variance", "ridge", "xgb"]
RANKING_MODELS = ["variance", "ridge", "xgb"]
RANKING_TIE_BREAK_ORDER = ["variance", "ridge", "xgb"]

EXPECTED_FILES = {
    RAW / "2017-05-12_batchdata_updated_struct_errorcorrect.mat": "9d928ab978f0e3c70b31cb833a749fedd35094d01af76475d69b40aa3497f5ba",
    RAW / "2017-06-30_batchdata_updated_struct_errorcorrect.mat": "63ab200d09ecb237fee5ef3a5c5db76e3212e3206a0bd92f769e1427fed338b8",
    SPLIT_MANIFEST: EXPECTED_SPLIT_MANIFEST_SHA,
    MEMBERSHIP_COMMITMENT: EXPECTED_MEMBERSHIP_COMMITMENT_SHA,
    SAMPLER_INPUT: EXPECTED_SAMPLER_INPUT_SHA,
    SAMPLER_RANKS: EXPECTED_SAMPLER_RANKS_SHA,
    SOURCE_MANIFEST: EXPECTED_SOURCE_MANIFEST_SHA,
    REPO / "configs/baselines/sklearn/dummy/matr_1.yaml": "1cc4c73b09412cb42a13ae2e143806f1d8a1d984bd38292a0077154071f02b2d",
    REPO / "configs/baselines/sklearn/variance_model/matr_1.yaml": "ab0849c3a021273629c1a6e90c09aa29eb425fdfb17aef2376888524f6984b5b",
    REPO / "configs/baselines/sklearn/ridge/matr_1.yaml": "ad554e8c459a85278ce125a20c179dd3ed65046d5abeab455a3738d3ca793a54",
    REPO / "configs/baselines/sklearn/xgb/matr_1.yaml": "ce3e35629429b988426d0a0b9da867e7c4411a949715dad61597b5684483a0f7",
    WHEELS / "addict-2.4.0-py3-none-any.whl": "249bb56bbfd3cdc2a004ea0ff4c2b6ddc84d53bc2194761636eb314d5cfa5dfc",
    WHEELS / "fire-0.7.1-py3-none-any.whl": "e43fd8a5033a9001e7e2973bab96070694b9f12f2e0ecf96d4683971b5ab1882",
}

EXPECTED_VERSIONS = {
    "python": "3.12.13",
    "numpy": "2.0.2",
    "pandas": "2.3.3",
    "torch": "2.10.0+cpu",
    "sklearn": "1.6.1",
    "xgboost": "3.2.0",
    "numba": "0.60.0",
    "scipy": "1.16.3",
    "h5py": "3.16.0",
}


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def mem_total_bytes() -> int:
    for line in Path("/proc/meminfo").read_text().splitlines():
        if line.startswith("MemTotal:"):
            return int(line.split()[1]) * 1024
    raise RuntimeError("MemTotal missing from /proc/meminfo")


def cgroup_memory_limit_bytes() -> int | None:
    for candidate in (
        Path("/sys/fs/cgroup/memory.max"),
        Path("/sys/fs/cgroup/memory/memory.limit_in_bytes"),
    ):
        if candidate.is_file():
            try:
                text = candidate.read_text().strip()
                if text != "max" and text.isdigit():
                    return int(text)
                elif text == "max":
                    return None
            except Exception:
                pass
    return None


def pip_freeze_sha() -> tuple[int, str]:
    sanitized_env = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
    text = subprocess.check_output(
        [sys.executable, "-m", "pip", "freeze"], text=True, env=sanitized_env
    )
    if not text.endswith("\n"):
        text += "\n"
    return len(text.splitlines()), hashlib.sha256(text.encode()).hexdigest()


def verify_environment() -> dict[str, object]:
    import h5py
    import numba
    import pandas
    import scipy
    import sklearn
    import torch
    import xgboost

    observed = {
        "python": platform.python_version(),
        "numpy": np.__version__,
        "pandas": pandas.__version__,
        "torch": torch.__version__,
        "sklearn": sklearn.__version__,
        "xgboost": xgboost.__version__,
        "numba": numba.__version__,
        "scipy": scipy.__version__,
        "h5py": h5py.__version__,
    }
    if observed != EXPECTED_VERSIONS:
        raise RuntimeError(f"environment mismatch: {observed!r}")
    if torch.cuda.is_available():
        raise RuntimeError("CPU-only environment required; CUDA is available")
    memory = mem_total_bytes()
    cpus = os.cpu_count() or 0
    if memory < MIN_RAM_BYTES:
        raise RuntimeError(f"RAM below frozen minimum: {memory}")
    if cpus != EXACT_CPUS:
        raise RuntimeError(
            f"exact CPU logical cores required: {EXACT_CPUS}, observed: {cpus}"
        )
    cgroup_limit = cgroup_memory_limit_bytes()
    xgb_params = (
        xgboost.XGBRegressor().get_params(deep=True)
        if hasattr(xgboost, "XGBRegressor")
        else {}
    )
    freeze_lines, freeze_sha = pip_freeze_sha()
    if (freeze_lines, freeze_sha) != (872, EXPECTED_BASE_FREEZE_SHA):
        raise RuntimeError(
            f"base pip freeze mismatch: lines={freeze_lines}, sha256={freeze_sha}"
        )
    return {
        "versions": observed,
        "cuda_available": False,
        "ram_total_bytes": memory,
        "cgroup_memory_limit_bytes": cgroup_limit,
        "logical_cpus": cpus,
        "exact_cpu_admission_pass": True,
        "xgboost_resolved_parameters": xgb_params,
        "base_pip_freeze_lines": freeze_lines,
        "base_pip_freeze_sha256": freeze_sha,
    }


def verify_source_snapshot() -> dict[str, object]:
    expected: list[tuple[str, str]] = []
    for line in SOURCE_MANIFEST.read_text().splitlines():
        digest, name = line.split("  ", 1)
        expected.append((name, digest))
    actual_names = sorted(
        str(path.relative_to(REPO)) for path in REPO.rglob("*") if path.is_file()
    )
    expected_names = [name for name, _ in expected]
    if actual_names != expected_names:
        raise RuntimeError("BatteryML source snapshot membership mismatch")
    for name, digest in expected:
        actual = sha256(REPO / name)
        if actual != digest:
            raise RuntimeError(f"BatteryML source mismatch: {name}: {actual}")
    return {
        "commit": "2861ae3b8c79938c7fc8e6fe9986b799ca71c7dd",
        "tracked_file_count": len(expected),
        "source_manifest_sha256": sha256(SOURCE_MANIFEST),
    }


def verify_governing_commitments() -> dict[str, object]:
    """Verify DP space count, reference rank, rank hashes, membership commitment, and manifest hash."""
    sys.path.insert(0, str(INPUT))
    from s3_sampler import S3Sampler

    sampler = S3Sampler(SAMPLER_INPUT)
    dp_count = sampler.total_minimum_cost_splits()
    if dp_count != EXPECTED_DP_COUNT:
        raise RuntimeError(f"DP count mismatch: {dp_count} != {EXPECTED_DP_COUNT}")

    ref_b = sampler.unrank(EXPECTED_S2_REF_RANK)
    if len(ref_b) != 83:
        raise RuntimeError(f"Reference split unranking invalid length: {len(ref_b)}")

    ranks_json = json.loads(SAMPLER_RANKS.read_text(encoding="utf-8"))
    draw_ranks = [item["rank"] for item in ranks_json]
    draw_bytes = "".join(f"{r}\n" for r in draw_ranks).encode("utf-8")
    draw_hash = hashlib.sha256(draw_bytes).hexdigest()
    if draw_hash != EXPECTED_DRAW_ORDER_HASH:
        raise RuntimeError(f"Draw order rank hash mismatch: {draw_hash} != {EXPECTED_DRAW_ORDER_HASH}")

    asc_ranks = sorted(draw_ranks)
    asc_bytes = "".join(f"{r}\n" for r in asc_ranks).encode("utf-8")
    asc_hash = hashlib.sha256(asc_bytes).hexdigest()
    if asc_hash != EXPECTED_ASCENDING_HASH:
        raise RuntimeError(f"Ascending rank hash mismatch: {asc_hash} != {EXPECTED_ASCENDING_HASH}")

    mem_hash = sha256(MEMBERSHIP_COMMITMENT)
    if mem_hash != EXPECTED_MEMBERSHIP_COMMITMENT_SHA:
        raise RuntimeError(f"Membership commitment hash mismatch: {mem_hash} != {EXPECTED_MEMBERSHIP_COMMITMENT_SHA}")

    man_hash = sha256(SPLIT_MANIFEST)
    if man_hash != EXPECTED_SPLIT_MANIFEST_SHA:
        raise RuntimeError(f"Split manifest hash mismatch: {man_hash} != {EXPECTED_SPLIT_MANIFEST_SHA}")

    return {
        "dp_count": dp_count,
        "s2_reference_rank": EXPECTED_S2_REF_RANK,
        "draw_order_hash": draw_hash,
        "ascending_hash": asc_hash,
        "membership_commitment_hash": mem_hash,
        "split_manifest_hash": man_hash,
        "governing_commitments_verified": True,
    }


def verify_inputs() -> dict[str, object]:
    hashes: dict[str, str] = {}
    for path, expected in EXPECTED_FILES.items():
        if not path.is_file():
            raise FileNotFoundError(f"Required input file missing: {path}")
        actual = sha256(path)
        if actual != expected:
            raise RuntimeError(f"SHA-256 mismatch for {path}: expected {expected}, got {actual}")
        try:
            label = str(path.relative_to(INPUT))
        except ValueError:
            label = f"public-raw/{path.name}"
        hashes[label] = actual
    return {
        "hashes": hashes,
        "source": verify_source_snapshot(),
        "commitments": verify_governing_commitments(),
    }


def read_receipt(path: Path) -> dict[str, str]:
    if not path.is_file():
        raise RuntimeError(f"Ratification receipt missing: {path}")
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if "=" in line:
            key, value = line.split("=", 1)
            values[key.strip()] = value.strip()
    required = {
        "status", "instance", "prereg_sha256", "driver_sha256",
        "split_manifest_sha256", "membership_commitment_sha256",
        "operator", "authorized_at", "operator_verbatim_statement",
        "operator_statement_location",
    }
    if not required.issubset(values):
        missing = required - set(values.keys())
        raise RuntimeError(f"Ratification receipt fields incomplete, missing: {missing}")
    if values["status"] != "RATIFIED" or values["instance"] != INSTANCE:
        raise RuntimeError("Ratification receipt does not authorize S3 execution")
    if not values.get("operator_verbatim_statement", "").strip():
        raise RuntimeError("Ratification receipt missing operator verbatim statement")
    if not values.get("operator_statement_location", "").strip():
        raise RuntimeError("Ratification receipt missing operator statement location")
    if sha256(PREREGISTRATION) != values["prereg_sha256"]:
        raise RuntimeError("Preregistration hash mismatch against ratification receipt")
    if sha256(DRIVER) != values["driver_sha256"]:
        raise RuntimeError("Driver hash mismatch against ratification receipt")
    if sha256(SPLIT_MANIFEST) != values["split_manifest_sha256"]:
        raise RuntimeError("Split manifest hash mismatch against ratification receipt")
    if sha256(MEMBERSHIP_COMMITMENT) != values["membership_commitment_sha256"]:
        raise RuntimeError("Membership commitment hash mismatch against ratification receipt")
    return values


def load_primary_split_a() -> tuple[list[str], list[str]]:
    with SAMPLER_INPUT.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    train = sorted([r["cell_id"] for r in rows if r["a_split"] == "train"])
    test = sorted([r["cell_id"] for r in rows if r["a_split"] == "test"])
    if (len(train), len(test)) != (41, 42):
        raise RuntimeError(f"Split A counts invalid: train={len(train)}, test={len(test)}")
    return train, test


def load_reference_split_b() -> tuple[list[str], list[str]]:
    sys.path.insert(0, str(INPUT))
    from s3_sampler import S3Sampler
    sampler = S3Sampler(SAMPLER_INPUT)
    assignments = sampler.unrank(EXPECTED_S2_REF_RANK)
    train = sorted([cid for cid, side in assignments.items() if side == "train"])
    test = sorted([cid for cid, side in assignments.items() if side == "test"])
    if (len(train), len(test)) != (41, 42):
        raise RuntimeError(f"Reference Split B counts invalid: train={len(train)}, test={len(test)}")
    return train, test


def load_all_sampled_splits() -> list[dict[str, Any]]:
    """Load all 64 sampled splits preserving draw_index, split_rank, and ascending rank sort order."""
    with SPLIT_MANIFEST.open(newline="", encoding="utf-8") as handle:
        all_rows = list(csv.DictReader(handle))

    splits_by_draw: dict[int, dict[str, Any]] = {}
    for r in all_rows:
        d_idx = int(r["split_index"])
        s_rank = int(r["split_rank"])
        cid = r["cell_id"]
        asgn = r["assignment"]
        if d_idx not in splits_by_draw:
            splits_by_draw[d_idx] = {
                "draw_index": d_idx,
                "split_rank": s_rank,
                "train": [],
                "test": [],
            }
        splits_by_draw[d_idx][asgn].append(cid)

    for d_idx, sdata in splits_by_draw.items():
        sdata["train"] = sorted(sdata["train"])
        sdata["test"] = sorted(sdata["test"])
        if (len(sdata["train"]), len(sdata["test"])) != (41, 42):
            raise RuntimeError(f"Draw index {d_idx} count mismatch: train={len(sdata['train'])}, test={len(sdata['test'])}")

    # Sort strictly by ascending split_rank
    ascending_splits = sorted(splits_by_draw.values(), key=lambda x: x["split_rank"])
    if len(ascending_splits) != 64:
        raise RuntimeError(f"Expected 64 sampled splits, got {len(ascending_splits)}")

    for pos, sdata in enumerate(ascending_splits, start=1):
        sdata["execution_position"] = pos

    return ascending_splits


def load_protocol_map() -> dict[str, str]:
    with SAMPLER_INPUT.open(newline="", encoding="utf-8") as handle:
        return {r["cell_id"]: r["protocol_sha256"] for r in csv.DictReader(handle)}


def install_extras() -> dict[str, str]:
    if SITE.exists():
        raise RuntimeError(f"Refusing existing site target: {SITE}")
    SITE.mkdir(parents=True, exist_ok=False)
    try:
        subprocess.run(
            [
                sys.executable, "-m", "pip", "install", "--no-index",
                "--no-deps", "--target", str(SITE),
                str(WHEELS / "addict-2.4.0-py3-none-any.whl"),
                str(WHEELS / "fire-0.7.1-py3-none-any.whl"),
            ],
            check=True,
            capture_output=True,
        )
    except Exception:
        import zipfile
        for whl in [WHEELS / "addict-2.4.0-py3-none-any.whl", WHEELS / "fire-0.7.1-py3-none-any.whl"]:
            with zipfile.ZipFile(whl, "r") as zf:
                zf.extractall(SITE)

    sys.path.insert(0, str(SITE))
    import addict
    import fire
    versions = {
        "addict": str(getattr(addict, "__version__", "2.4.0")),
        "fire": str(getattr(fire, "__version__", "0.7.1")),
    }
    if versions != {"addict": "2.4.0", "fire": "0.7.1"}:
        raise RuntimeError(f"Offline extras version mismatch: {versions!r}")
    return versions


def activate_extras() -> None:
    if not SITE.is_dir():
        raise RuntimeError("Offline extras target directory is missing")
    sys.path.insert(0, str(SITE))
    import addict
    import fire
    if str(getattr(addict, "__version__", "2.4.0")) != "2.4.0":
        raise RuntimeError("addict version mismatch")
    if str(getattr(fire, "__version__", "0.7.1")) != "0.7.1":
        raise RuntimeError("fire version mismatch")
    site_resolved = SITE.resolve()
    for mod, name in ((addict, "addict"), (fire, "fire")):
        mod_file = getattr(mod, "__file__", None)
        if not mod_file:
            raise RuntimeError(f"{name} missing __file__ attribute")
        mod_path = Path(mod_file).resolve()
        if not mod_path.is_relative_to(site_resolved):
            raise RuntimeError(
                f"{name} provenance violation: loaded from {mod_path}, expected within {site_resolved}"
            )


def processed_rows() -> list[tuple[str, str]]:
    files = sorted(PROCESSED.glob("MATR_*.pkl"))
    if len(files) != 89:
        raise RuntimeError(f"Expected 89 processed cells, found {len(files)}")
    return [(path.name, sha256(path)) for path in files]


def verify_processed() -> str:
    manifest = PROCESSED / "processed-files.sha256"
    expected = []
    for line in manifest.read_text(encoding="utf-8").splitlines():
        digest, name = line.split("  ", 1)
        expected.append((name, digest))
    if processed_rows() != expected:
        raise RuntimeError("Processed file manifest mismatch")
    return sha256(manifest)


def clean_cell_id(value: str) -> str:
    return value.removeprefix("MATR_")


def command_preprocess(args: argparse.Namespace) -> None:
    ratification = read_receipt(args.ratification_receipt)
    environment = verify_environment()
    inputs = verify_inputs()
    activate_extras()
    if PROCESSED.exists():
        raise RuntimeError(f"Refusing existing preprocessing directory: {PROCESSED}")
    PROCESSED.mkdir(parents=True, exist_ok=False)
    sys.path.insert(0, str(REPO))
    from batteryml.preprocess.base import BasePreprocessor
    from batteryml.preprocess.preprocess_MATR import clean_batches, load_batch

    preprocessor = BasePreprocessor(output_dir=str(PROCESSED), silent=True)
    batches = [
        load_batch(RAW / "2017-05-12_batchdata_updated_struct_errorcorrect.mat", 1),
        load_batch(RAW / "2017-06-30_batchdata_updated_struct_errorcorrect.mat", 2),
    ]
    clean_batches(batches, preprocessor.dump_single_file, True)
    rows = processed_rows()
    manifest = PROCESSED / "processed-files.sha256"
    manifest.write_text("".join(f"{digest}  {name}\n" for name, digest in rows), encoding="utf-8")
    receipt = {
        "timestamp_utc": utcnow(),
        "ratification": ratification,
        "environment": environment,
        "inputs": inputs,
        "processed_file_count": len(rows),
        "processed_manifest_sha256": sha256(manifest),
    }
    (PROCESSED / "preprocess-receipt.json").write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def execute_single_fit(
    output_dir: Path,
    split_type: str,
    draw_index: int | None,
    split_rank: int | None,
    execution_position: int | None,
    model_name: str,
    train_ids: list[str],
    test_ids: list[str],
    protocol_map: dict[str, str],
    split_a_test_set: set[str],
    split_a_predictions: dict[str, dict[str, float]] | None = None,
) -> dict[str, Any]:
    """Execute training of model_name on train_ids, predict test_ids (42) and b2c1 without refitting."""
    activate_extras()
    output_dir.mkdir(parents=True, exist_ok=False)

    os.chdir(REPO)
    sys.path.insert(0, str(REPO))
    from batteryml.builders import MODELS as MODEL_REGISTRY
    from batteryml.pipeline import load_config, set_seed
    from batteryml.task import Task
    from batteryml.train_test_split.MATR_split import MATRTrainTestSplitter

    # 1. Primary evaluation task (41 train, 42 test)
    splitter_primary = MATRTrainTestSplitter(str(PROCESSED), train_ids, test_ids)
    path_train = [path.stem.split("_", 1)[1] for path in splitter_primary.train_cells]
    path_test = [path.stem.split("_", 1)[1] for path in splitter_primary.test_cells]
    if path_train != train_ids or path_test != test_ids:
        raise RuntimeError("Splitter primary membership/order mismatch")

    config = load_config(str(MODELS[model_name]), str(output_dir))
    task_primary = Task(
        train_test_splitter=splitter_primary,
        feature_extractor=config["feature"],
        label_annotator=config["label"],
        feature_transformation=config["feature_transformation"],
        label_transformation=config["label_transformation"],
    )
    dataset_primary = task_primary.build().to("cpu")
    loaded_train = [clean_cell_id(cell.cell_id) for cell in task_primary.train_cells]
    loaded_test = [clean_cell_id(cell.cell_id) for cell in task_primary.test_cells]
    if loaded_train != train_ids or loaded_test != test_ids:
        raise RuntimeError("Loaded primary membership/order mismatch before fit")
    if len(dataset_primary.train_data) != len(train_ids) or len(dataset_primary.test_data) != len(test_ids):
        raise RuntimeError("Label filtering changed frozen membership")

    # Fit model with seed 0
    set_seed(0)
    model = MODEL_REGISTRY.build(config["model"])
    model.workspace = output_dir
    resolved = model.model.get_params(deep=True) if hasattr(model, "model") else {}
    (output_dir / "resolved-model-parameters.json").write_text(
        json.dumps(resolved, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )

    model.fit(dataset_primary, timestamp="frozen")

    ckpt_path = output_dir / "frozen.ckpt"
    if not ckpt_path.is_file():
        raise RuntimeError("Model fit did not produce frozen.ckpt")
    ckpt_sha_before = sha256(ckpt_path)

    # Predict primary test set (42 cells)
    pred_primary_1 = model.predict(dataset_primary)
    target_primary = dataset_primary.test_data.label
    if dataset_primary.label_transformation is not None:
        target_primary = dataset_primary.label_transformation.inverse_transform(target_primary)
        pred_primary_1 = dataset_primary.label_transformation.inverse_transform(pred_primary_1)
    targets_42 = target_primary.detach().cpu().numpy().reshape(-1)
    preds_42_before = pred_primary_1.detach().cpu().numpy().reshape(-1)

    rmse_primary = float(np.sqrt(np.mean((targets_42 - preds_42_before) ** 2)))
    mae_primary = float(np.mean(np.abs(targets_42 - preds_42_before)))

    # 2. b2c1 Outlier evaluation WITHOUT refitting
    splitter_b2c1 = MATRTrainTestSplitter(str(PROCESSED), train_ids, ["b2c1"])
    task_b2c1 = Task(
        train_test_splitter=splitter_b2c1,
        feature_extractor=config["feature"],
        label_annotator=config["label"],
        feature_transformation=config["feature_transformation"],
        label_transformation=config["label_transformation"],
    )
    dataset_b2c1 = task_b2c1.build().to("cpu")
    pred_b2c1_tensor = model.predict(dataset_b2c1)
    target_b2c1_tensor = dataset_b2c1.test_data.label
    if dataset_b2c1.label_transformation is not None:
        target_b2c1_tensor = dataset_b2c1.label_transformation.inverse_transform(target_b2c1_tensor)
        pred_b2c1_tensor = dataset_b2c1.label_transformation.inverse_transform(pred_b2c1_tensor)
    target_b2c1 = float(target_b2c1_tensor.detach().cpu().numpy().reshape(-1)[0])
    pred_b2c1 = float(pred_b2c1_tensor.detach().cpu().numpy().reshape(-1)[0])

    # Re-predict primary to strictly verify byte-identical output (B2C1_LIFT_INVALID check)
    pred_primary_2 = model.predict(dataset_primary)
    if dataset_primary.label_transformation is not None:
        pred_primary_2 = dataset_primary.label_transformation.inverse_transform(pred_primary_2)
    preds_42_after = pred_primary_2.detach().cpu().numpy().reshape(-1)

    if not np.array_equal(preds_42_before, preds_42_after):
        raise RuntimeError("B2C1_LIFT_INVALID: primary predictions altered after b2c1 evaluation")

    ckpt_sha_after = sha256(ckpt_path)
    if ckpt_sha_before != ckpt_sha_after:
        raise RuntimeError("B2C1_LIFT_INVALID: model checkpoint altered after b2c1 evaluation")

    # Prune binary checkpoint to honor public text evidence budget
    ckpt_path.unlink()

    # Lifted 43-cell metrics
    targets_43 = np.append(targets_42, target_b2c1)
    preds_43 = np.append(preds_42_before, pred_b2c1)
    rmse_lifted = float(np.sqrt(np.mean((targets_43 - preds_43) ** 2)))
    mae_lifted = float(np.mean(np.abs(targets_43 - preds_43)))
    b2c1_influence_j = (rmse_lifted - rmse_primary) / rmse_primary

    # 3. Error concentrations (Cell-level Top-3 SSE, Protocol-level Top-1 SSE)
    squared_errors = (targets_42 - preds_42_before) ** 2
    total_sse = float(np.sum(squared_errors))
    sorted_se = sorted(squared_errors, reverse=True)
    top3_sse = float(np.sum(sorted_se[:3]))
    cell_top3_sse_concentration = top3_sse / total_sse if total_sse > 0 else 0.0

    proto_sse: dict[str, float] = {}
    for cid, se in zip(test_ids, squared_errors):
        p_sha = protocol_map[cid]
        proto_sse[p_sha] = proto_sse.get(p_sha, 0.0) + float(se)
    max_proto_sse = max(proto_sse.values()) if proto_sse else 0.0
    protocol_top1_sse_concentration = max_proto_sse / total_sse if total_sse > 0 else 0.0

    # Save per-cell predictions for 42 cells
    with (output_dir / "per-cell-predictions.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "split_type", "draw_index", "split_rank", "execution_position",
                "model", "cell_id", "protocol_sha256", "target", "prediction",
            ],
        )
        writer.writeheader()
        for cid, y_obs, y_pred in zip(test_ids, targets_42, preds_42_before):
            writer.writerow({
                "split_type": split_type,
                "draw_index": str(draw_index) if draw_index is not None else "",
                "split_rank": str(split_rank) if split_rank is not None else "",
                "execution_position": str(execution_position) if execution_position is not None else "",
                "model": model_name,
                "cell_id": cid,
                "protocol_sha256": protocol_map[cid],
                "target": repr(float(y_obs)),
                "prediction": repr(float(y_pred)),
            })

    # Save b2c1 record
    b2c1_record = {
        "cell_id": "b2c1",
        "target": target_b2c1,
        "prediction": pred_b2c1,
        "rmse_primary": rmse_primary,
        "rmse_lifted_43": rmse_lifted,
        "b2c1_influence_j": b2c1_influence_j,
        "mae_primary": mae_primary,
        "mae_lifted_43": mae_lifted,
        "checkpoint_byte_identity_verified": True,
    }
    (output_dir / "b2c1-prediction.json").write_text(
        json.dumps(b2c1_record, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    # 4. Paired diagnostic P_mk on 32-cell intersection
    paired_diagnostic = None
    intersection_cells = sorted(list(set(test_ids) & split_a_test_set))
    if len(intersection_cells) != 32 and split_type in ("sampled", "ref_b"):
        raise RuntimeError(
            f"INTERSECTION_INVARIANT_FAILURE: intersection with Split A test is {len(intersection_cells)}, expected 32"
        )
    if split_a_predictions is not None and len(intersection_cells) == 32:
        cur_cell_preds = {cid: p for cid, p in zip(test_ids, preds_42_before)}
        cur_cell_targets = {cid: y for cid, y in zip(test_ids, targets_42)}

        cur_errors_sq = [(cur_cell_targets[cid] - cur_cell_preds[cid]) ** 2 for cid in intersection_cells]
        rmse_intersection_cur = float(np.sqrt(np.mean(cur_errors_sq)))

        a_cell_preds = split_a_predictions[model_name]
        a_errors_sq = [(cur_cell_targets[cid] - a_cell_preds[cid]) ** 2 for cid in intersection_cells]
        rmse_intersection_a = float(np.sqrt(np.mean(a_errors_sq)))

        p_rmse = (rmse_intersection_cur - rmse_intersection_a) / rmse_intersection_a
        paired_diagnostic = {
            "intersection_size": 32,
            "rmse_intersection_split": rmse_intersection_cur,
            "rmse_intersection_split_a": rmse_intersection_a,
            "paired_relative_p_rmse": p_rmse,
        }

    receipt = {
        "timestamp_utc": utcnow(),
        "split_type": split_type,
        "draw_index": draw_index,
        "split_rank": split_rank,
        "execution_position": execution_position,
        "model": model_name,
        "seed": 0,
        "train_cell_ids": train_ids,
        "test_cell_ids": test_ids,
        "rmse": rmse_primary,
        "mae": mae_primary,
        "rmse_lifted_43": rmse_lifted,
        "mae_lifted_43": mae_lifted,
        "b2c1_influence_j": b2c1_influence_j,
        "cell_top3_sse_concentration": cell_top3_sse_concentration,
        "protocol_top1_sse_concentration": protocol_top1_sse_concentration,
        "checkpoint_sha256": ckpt_sha_before,
        "paired_diagnostic": paired_diagnostic,
    }
    (output_dir / "run-receipt.json").write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    return {
        "rmse": rmse_primary,
        "mae": mae_primary,
        "rmse_lifted": rmse_lifted,
        "mae_lifted": mae_lifted,
        "b2c1_j": b2c1_influence_j,
        "cell_top3_sse": cell_top3_sse_concentration,
        "protocol_top1_sse": protocol_top1_sse_concentration,
        "predictions": {cid: float(p) for cid, p in zip(test_ids, preds_42_before)},
        "targets": {cid: float(y) for cid, y in zip(test_ids, targets_42)},
        "paired_diagnostic": paired_diagnostic,
    }


def command_execute_all(args: argparse.Namespace) -> None:
    attempt = getattr(args, "attempt", 1)
    if attempt not in (1, 2):
        raise ValueError(f"Attempt must be 1 or 2, got {attempt}")
    kernel_id = getattr(args, "kernel_id", "").strip()
    if not kernel_id:
        raise ValueError("--kernel-id is required for execute-all")

    ratification = read_receipt(args.ratification_receipt)
    environment = verify_environment()
    inputs = verify_inputs()

    if ARTIFACT.exists() or PROCESSED.exists() or SITE.exists():
        raise RuntimeError("Refusing pre-existing S3 execution namespace in /kaggle/working")

    ARTIFACT.mkdir(parents=True, exist_ok=False)

    start_time = utcnow()
    ledger_entry: dict[str, object] = {
        "attempt_number": attempt,
        "kaggle_kernel_run_id_or_url": kernel_id,
        "start_utc": start_time,
        "end_utc": None,
        "governing_commit": GOVERNING_FROZEN_COMMIT,
        "governing_prereg_sha256": sha256(PREREGISTRATION),
        "governing_driver_sha256": sha256(DRIVER),
        "governing_split_manifest_sha256": sha256(SPLIT_MANIFEST),
        "governing_membership_commitment_sha256": sha256(MEMBERSHIP_COMMITMENT),
        "exit_code": None,
        "disposition": None,
        "generated_receipts": [],
    }
    (ARTIFACT / "attempt-ledger.json").write_text(
        json.dumps(ledger_entry, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    extras = install_extras()
    closure = {
        "timestamp_utc": utcnow(),
        "attempt": attempt,
        "ratification": ratification,
        "environment": environment,
        "inputs": inputs,
        "offline_extras": extras,
        "driver_sha256": sha256(DRIVER),
        "preregistration_sha256": sha256(PREREGISTRATION),
    }
    (ARTIFACT / "execution-closure.json").write_text(
        json.dumps(closure, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    protocol_map = load_protocol_map()
    train_a, test_a = load_primary_split_a()
    split_a_test_set = set(test_a)

    try:
        # Step 1: Preprocess raw data
        print(f"[{utcnow()}] [S3-DRIVER] Preprocessing MATR batches into {PROCESSED}...")
        command_preprocess(args)
        processed_sha = verify_processed()
        print(f"[{utcnow()}] [S3-DRIVER] Preprocessing verified, manifest SHA: {processed_sha}")

        # Step 2: Split A Positive Control Baseline (4 models)
        print(f"[{utcnow()}] [S3-DRIVER] Executing Split A baseline fits (Positive Control Gate 1)...")
        split_a_results: dict[str, Any] = {}
        split_a_predictions: dict[str, dict[str, float]] = {}

        for model in ORDERED_MODELS:
            out_dir = ARTIFACT / "results" / "split_a" / model
            res = execute_single_fit(
                output_dir=out_dir,
                split_type="split_a",
                draw_index=None,
                split_rank=None,
                execution_position=None,
                model_name=model,
                train_ids=train_a,
                test_ids=test_a,
                protocol_map=protocol_map,
                split_a_test_set=split_a_test_set,
            )
            split_a_results[model] = res
            split_a_predictions[model] = res["predictions"]
            print(f"[{utcnow()}] [S3-DRIVER] Split A | Model: {model:<8} | COMPLETE | Status: PASS")

        # Positive Control Gate 1 Verification
        gate_1_divergences = {}
        gate_1_failed = False
        for model in RANKING_MODELS:
            observed_rmse = split_a_results[model]["rmse"]
            ref_rmse = S2_1_A_REFERENCE_RMSE[model]
            rel_diff = abs(observed_rmse - ref_rmse) / ref_rmse
            passed = rel_diff <= CONTROL_GATE_REL_TOLERANCE
            gate_1_divergences[model] = {
                "observed_rmse": observed_rmse,
                "reference_rmse": ref_rmse,
                "relative_diff": rel_diff,
                "passed": passed,
            }
            if not passed:
                gate_1_failed = True

        gate_1_receipt = {
            "timestamp_utc": utcnow(),
            "gate": "GATE_1_SPLIT_A_POSITIVE_CONTROL",
            "relative_tolerance": CONTROL_GATE_REL_TOLERANCE,
            "divergences": gate_1_divergences,
            "status": "PASS" if not gate_1_failed else "HARD_STOP_A_POSITIVE_CONTROL_DIVERGENCE",
        }
        (ARTIFACT / "gate-1-positive-control-a.json").write_text(
            json.dumps(gate_1_receipt, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        if gate_1_failed:
            raise RuntimeError(
                f"HARD_STOP_A_POSITIVE_CONTROL_DIVERGENCE: Split A RMSE diverged by >1.0%: {gate_1_divergences}"
            )
        print(f"[{utcnow()}] [S3-DRIVER] Positive Control Gate 1 PASSED.")

        # Step 3: S2.1 Reference Split B Control (4 models)
        print(f"[{utcnow()}] [S3-DRIVER] Executing S2.1 Reference Split B fits (Positive Control Gate 2)...")
        train_ref_b, test_ref_b = load_reference_split_b()
        ref_b_results: dict[str, Any] = {}

        for model in ORDERED_MODELS:
            out_dir = ARTIFACT / "results" / "ref_b" / model
            res = execute_single_fit(
                output_dir=out_dir,
                split_type="ref_b",
                draw_index=None,
                split_rank=EXPECTED_S2_REF_RANK,
                execution_position=None,
                model_name=model,
                train_ids=train_ref_b,
                test_ids=test_ref_b,
                protocol_map=protocol_map,
                split_a_test_set=split_a_test_set,
                split_a_predictions=split_a_predictions,
            )
            ref_b_results[model] = res
            print(f"[{utcnow()}] [S3-DRIVER] Ref B   | Model: {model:<8} | COMPLETE | Status: PASS")

        # Positive Control Gate 2 Verification
        gate_2_divergences = {}
        gate_2_failed = False
        for model in RANKING_MODELS:
            observed_rmse = ref_b_results[model]["rmse"]
            ref_rmse = S2_1_B_REFERENCE_RMSE[model]
            rel_diff = abs(observed_rmse - ref_rmse) / ref_rmse
            passed = rel_diff <= CONTROL_GATE_REL_TOLERANCE
            gate_2_divergences[model] = {
                "observed_rmse": observed_rmse,
                "reference_rmse": ref_rmse,
                "relative_diff": rel_diff,
                "passed": passed,
            }
            if not passed:
                gate_2_failed = True

        gate_2_receipt = {
            "timestamp_utc": utcnow(),
            "gate": "GATE_2_REFERENCE_SPLIT_B_CONTROL",
            "relative_tolerance": CONTROL_GATE_REL_TOLERANCE,
            "divergences": gate_2_divergences,
            "status": "PASS" if not gate_2_failed else "HARD_STOP_REFERENCE_SPLIT_DIVERGENCE",
        }
        (ARTIFACT / "gate-2-reference-split-b.json").write_text(
            json.dumps(gate_2_receipt, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        if gate_2_failed:
            raise RuntimeError(
                f"HARD_STOP_REFERENCE_SPLIT_DIVERGENCE: S2.1 Reference Split B RMSE diverged by >1.0%: {gate_2_divergences}"
            )
        print(f"[{utcnow()}] [S3-DRIVER] Positive Control Gate 2 PASSED.")

        # Step 4: 256 Sampled Model Fits (K=64 splits x 4 models in ascending split_rank order)
        sampled_splits = load_all_sampled_splits()
        print(f"[{utcnow()}] [S3-DRIVER] Executing 256 Sampled Model Fits across K=64 splits in ascending split_rank order...")

        model_relative_changes: dict[str, list[float]] = {m: [] for m in RANKING_MODELS}
        dummy_relative_changes: list[float] = []
        split_ranks_eval: list[list[str]] = []
        split_summaries: list[dict[str, Any]] = []

        sys.path.insert(0, str(INPUT))
        from s3_adjudication import (
            adjudicate_s3,
            compute_dummy_skill,
            compute_operational_d,
            compute_quantiles_type_7,
            sort_models_by_rmse,
        )

        baseline_rank = sort_models_by_rmse(
            {m: split_a_results[m]["rmse"] for m in RANKING_MODELS},
            models=RANKING_MODELS,
            tie_break_order=RANKING_TIE_BREAK_ORDER,
        )

        for sdata in sampled_splits:
            pos = sdata["execution_position"]
            d_idx = sdata["draw_index"]
            s_rank = sdata["split_rank"]
            train_k = sdata["train"]
            test_k = sdata["test"]

            split_dir_name = f"pos_{pos:02d}_rank_{s_rank:06d}_draw_{d_idx:02d}"
            split_models_res: dict[str, Any] = {}

            for model in ORDERED_MODELS:
                out_dir = ARTIFACT / "results" / "sampled" / split_dir_name / model
                res = execute_single_fit(
                    output_dir=out_dir,
                    split_type="sampled",
                    draw_index=d_idx,
                    split_rank=s_rank,
                    execution_position=pos,
                    model_name=model,
                    train_ids=train_k,
                    test_ids=test_k,
                    protocol_map=protocol_map,
                    split_a_test_set=split_a_test_set,
                    split_a_predictions=split_a_predictions,
                )
                split_models_res[model] = res
                # Blindness protection: log progress without numeric metrics in stdout
                print(f"[{utcnow()}] [S3-DRIVER] [Pos {pos:02d}/64 | Rank {s_rank:06d} | Draw {d_idx:02d} | Model: {model:<8} | COMPLETE | Status: PASS]")

            # Estimands & diagnostics
            split_model_d_rmse = {}
            split_model_d_mae = {}
            for m in RANKING_MODELS:
                d_rmse = compute_operational_d(split_models_res[m]["rmse"], split_a_results[m]["rmse"])
                d_mae = (split_models_res[m]["mae"] - split_a_results[m]["mae"]) / split_a_results[m]["mae"]
                model_relative_changes[m].append(d_rmse)
                split_model_d_rmse[m] = d_rmse
                split_model_d_mae[m] = d_mae

            dummy_d = compute_operational_d(split_models_res["dummy"]["rmse"], split_a_results["dummy"]["rmse"])
            dummy_relative_changes.append(dummy_d)

            k_rank = sort_models_by_rmse(
                {m: split_models_res[m]["rmse"] for m in RANKING_MODELS},
                models=RANKING_MODELS,
                tie_break_order=RANKING_TIE_BREAK_ORDER,
            )
            split_ranks_eval.append(k_rank)

            split_skills = {
                m: compute_dummy_skill(split_models_res[m]["rmse"], split_models_res["dummy"]["rmse"])
                for m in RANKING_MODELS
            }

            split_summary = {
                "execution_position": pos,
                "draw_index": d_idx,
                "split_rank": s_rank,
                "ranking_order": k_rank,
                "rank_changed_vs_baseline": k_rank != baseline_rank,
                "d_rmse": split_model_d_rmse,
                "d_mae": split_model_d_mae,
                "dummy_d_rmse": dummy_d,
                "skills": split_skills,
                "b2c1_j": {m: split_models_res[m]["b2c1_j"] for m in ORDERED_MODELS},
                "cell_top3_sse": {m: split_models_res[m]["cell_top3_sse"] for m in ORDERED_MODELS},
                "protocol_top1_sse": {m: split_models_res[m]["protocol_top1_sse"] for m in ORDERED_MODELS},
                "paired_diagnostic": {m: split_models_res[m]["paired_diagnostic"] for m in ORDERED_MODELS},
            }
            split_summaries.append(split_summary)
            (ARTIFACT / "results" / "sampled" / split_dir_name / "split-summary.json").write_text(
                json.dumps(split_summary, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )

        # Step 5: Candidate Adjudication (Governing adjudication produced post-binding)
        print(f"[{utcnow()}] [S3-DRIVER] Evaluating candidate adjudication...")
        candidate_decision = adjudicate_s3(
            model_relative_changes=model_relative_changes,
            baseline_rank=baseline_rank,
            split_ranks=split_ranks_eval,
            dummy_relative_changes=dummy_relative_changes,
        )

        CENTRAL_QUANTILES = [0.25, 0.50, 0.75]
        TAIL_QUANTILES = [0.05, 0.95]
        TAIL_REPORTING_MINIMUM_K = 40

        k_count = len(split_ranks_eval)
        tails_eligible = k_count >= TAIL_REPORTING_MINIMUM_K
        quantiles_to_eval = sorted(CENTRAL_QUANTILES + (TAIL_QUANTILES if tails_eligible else []))

        d_rmse_quantiles = {
            m: compute_quantiles_type_7(model_relative_changes[m], quantiles_to_eval)
            for m in RANKING_MODELS
        }
        dummy_d_quantiles = compute_quantiles_type_7(dummy_relative_changes, quantiles_to_eval)

        candidate_payload = {
            "timestamp_utc": utcnow(),
            "status": "CANDIDATE_ADJUDICATION",
            "note": "Candidate adjudication from execution host; governing adjudication requires post-run content binding",
            "instance": INSTANCE,
            "governing_commit": GOVERNING_FROZEN_COMMIT,
            "baseline_rank": baseline_rank,
            "adjudication": candidate_decision,
            "d_rmse_quantiles": d_rmse_quantiles,
            "dummy_d_quantiles": dummy_d_quantiles,
            "split_summaries": split_summaries,
        }
        (ARTIFACT / "adjudication_candidate.json").write_text(
            json.dumps(candidate_payload, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

        # Step 6: Artifact manifest and completion receipt
        manifest_path = ARTIFACT / "artifact-files.sha256"
        all_artifact_files = sorted(p for p in ARTIFACT.rglob("*") if p.is_file() and p != manifest_path)
        manifest_content = "".join(f"{sha256(p)}  {p.relative_to(ARTIFACT)}\n" for p in all_artifact_files)
        manifest_path.write_text(manifest_content, encoding="utf-8")
        manifest_sha = sha256(manifest_path)

        completion_receipt = {
            "timestamp_utc": utcnow(),
            "attempt": attempt,
            "status": "COMPLETE",
            "instance": INSTANCE,
            "candidate_adjudication": candidate_decision["adjudication_category"],
            "artifact_manifest_sha256": manifest_sha,
            "total_files": len(all_artifact_files),
        }
        (ARTIFACT / "completion-receipt.json").write_text(
            json.dumps(completion_receipt, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

        ledger_entry["end_utc"] = utcnow()
        ledger_entry["exit_code"] = 0
        ledger_entry["disposition"] = "GOVERNING_COMPLETE"
        ledger_entry["generated_receipts"] = [
            "execution-closure.json",
            "gate-1-positive-control-a.json",
            "gate-2-reference-split-b.json",
            "adjudication_candidate.json",
            "completion-receipt.json",
            "artifact-files.sha256",
        ]
        (ARTIFACT / "attempt-ledger.json").write_text(
            json.dumps(ledger_entry, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        print(f"[{utcnow()}] [S3-DRIVER] Execution completed successfully. Manifest SHA: {manifest_sha}")

    except Exception as exc:
        ledger_entry["end_utc"] = utcnow()
        ledger_entry["exit_code"] = 1
        ledger_entry["disposition"] = (
            "FAILED_PENDING_OPERATOR_RATIFICATION"
            if attempt == 1
            else "EXECUTION_BLOCKED_RESOURCE"
        )
        (ARTIFACT / "attempt-ledger.json").write_text(
            json.dumps(ledger_entry, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        raise exc


def command_verify(_: argparse.Namespace) -> None:
    receipt = {
        "timestamp_utc": utcnow(),
        "status": "PASS",
        "scientific_run_executed": False,
        "environment": verify_environment(),
        "inputs": verify_inputs(),
    }
    print(json.dumps(receipt, indent=2, sort_keys=True))


def command_verify_determinism(_: argparse.Namespace) -> None:
    if not SITE.is_dir():
        install_extras()
    activate_extras()
    sys.path.insert(0, str(REPO))
    from batteryml.data.battery_data import BatteryData, CycleData
    from batteryml.builders import MODELS as MODEL_BUILDERS
    from batteryml.train_test_split.base import BaseTrainTestSplitter
    from batteryml.task import Task
    from batteryml.pipeline import set_seed

    def run_pass(output_dir: Path) -> dict[str, dict[str, object]]:
        tmp_data = output_dir / "data"
        tmp_data.mkdir(parents=True, exist_ok=True)
        train_paths, test_paths = [], []
        cells_spec = [
            ("synth_1", 800.0, 0.01, True),
            ("synth_2", 900.0, 0.02, True),
            ("synth_3", 750.0, -0.01, False),
            ("synth_4", 850.0, -0.02, False),
        ]
        for cid, life, noise, is_tr in cells_spec:
            cycles = []
            for c in range(105):
                q = np.linspace(1.1 - 0.001 * c + noise, 0.1, 1000)
                cd = CycleData(
                    cycle_number=c,
                    Qdlin=q.tolist(),
                    discharge_capacity_in_Ah=[float(q[0])],
                )
                cycles.append(cd)
            b = BatteryData(
                cell_id=cid,
                cycle_data=cycles,
                nominal_capacity_in_Ah=1.1,
                max_cycle=life,
            )
            p = tmp_data / f"{cid}.pkl"
            b.dump(p)
            if is_tr:
                train_paths.append(p)
            else:
                test_paths.append(p)

        class Splitter(BaseTrainTestSplitter):
            def __init__(self):
                super().__init__(str(tmp_data))
                self.train_cells = train_paths
                self.test_cells = test_paths

            def split(self):
                return self.train_cells, self.test_cells

        splitter = Splitter()
        model_configs = [
            (
                "dummy",
                "DummyRULPredictor",
                {
                    "name": "VarianceModelFeatureExtractor",
                    "interp_dims": 1000,
                    "critical_cycles": [2, 9, 99],
                    "use_precalculated_qdlin": True,
                },
            ),
            (
                "variance",
                "LinearRegressionRULPredictor",
                {
                    "name": "VarianceModelFeatureExtractor",
                    "interp_dims": 1000,
                    "critical_cycles": [2, 9, 99],
                    "use_precalculated_qdlin": True,
                },
            ),
            (
                "ridge",
                "RidgeRULPredictor",
                {
                    "name": "VoltageCapacityMatrixFeatureExtractor",
                    "diff_base": 8,
                    "max_cycle_index": 98,
                    "cycles_to_keep": 98,
                    "use_precalculated_qdlin": True,
                },
            ),
            (
                "xgb",
                "XGBoostRULPredictor",
                {
                    "name": "VoltageCapacityMatrixFeatureExtractor",
                    "diff_base": 8,
                    "max_cycle_index": 98,
                    "cycles_to_keep": 98,
                    "use_precalculated_qdlin": True,
                },
            ),
        ]
        results = {}
        for short_name, mname, f_conf in model_configs:
            task = Task(
                train_test_splitter=splitter,
                feature_extractor=f_conf,
                label_annotator={"name": "RULLabelAnnotator"},
                feature_transformation={"name": "ZScoreDataTransformation"},
                label_transformation={
                    "name": "SequentialDataTransformation",
                    "transformations": [
                        {"name": "LogScaleDataTransformation"},
                        {"name": "ZScoreDataTransformation"},
                    ],
                },
            )
            dataset = task.build().to("cpu")
            set_seed(0)
            model = MODEL_BUILDERS.build({"name": mname})
            m_workspace = output_dir / short_name
            m_workspace.mkdir(parents=True, exist_ok=True)
            model.workspace = m_workspace
            model.fit(dataset, timestamp="frozen")
            pred = model.predict(dataset)
            target = dataset.test_data.label
            if dataset.label_transformation is not None:
                pred = dataset.label_transformation.inverse_transform(pred)
                target = dataset.label_transformation.inverse_transform(target)
            target_vals = target.detach().cpu().numpy().reshape(-1)
            pred_vals = pred.detach().cpu().numpy().reshape(-1)
            rmse = float(np.sqrt(np.mean((target_vals - pred_vals) ** 2)))
            mae = float(np.mean(np.abs(target_vals - pred_vals)))

            preds_path = output_dir / f"{short_name}_predictions.csv"
            with open(preds_path, "w", newline="", encoding="utf-8") as h:
                w = csv.writer(h)
                w.writerow(["cell_id", "target", "prediction"])
                for cid, obs, pr in zip(["synth_3", "synth_4"], target_vals, pred_vals):
                    w.writerow([cid, repr(float(obs)), repr(float(pr))])

            metrics_path = output_dir / f"{short_name}_metrics.json"
            with open(metrics_path, "w", encoding="utf-8") as h:
                json.dump({"rmse": rmse, "mae": mae}, h, indent=2, sort_keys=True)

            results[short_name] = {
                "predictions_sha256": hashlib.sha256(preds_path.read_bytes()).hexdigest(),
                "metrics_sha256": hashlib.sha256(metrics_path.read_bytes()).hexdigest(),
                "metrics": {"rmse": rmse, "mae": mae},
            }
        return results

    base_tmp = Path(tempfile.mkdtemp())
    try:
        res1 = run_pass(base_tmp / "pass1")
        res2 = run_pass(base_tmp / "pass2")
        match = (res1 == res2)
        receipt = {
            "timestamp_utc": utcnow(),
            "status": "PASS" if match else "FAIL",
            "rule": "rename_rerun_byte_identical",
            "scope": {
                "fixture_type": "synthetic_non_matr_cells",
                "models_verified": ["dummy", "variance", "ridge", "xgb"],
                "comparison": ["predictions.csv", "metrics.json"],
            },
            "byte_identical_match": match,
            "canonical_metrics": {k: v["metrics"] for k, v in res1.items()},
        }
        print(json.dumps(receipt, indent=2, sort_keys=True))
    finally:
        shutil.rmtree(base_tmp)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)

    verify = subparsers.add_parser("verify")
    verify.set_defaults(func=command_verify)

    preprocess = subparsers.add_parser("preprocess-one")
    preprocess.add_argument("--ratification-receipt", type=Path, required=True)
    preprocess.set_defaults(func=command_preprocess)

    execute = subparsers.add_parser("execute-all")
    execute.add_argument("--ratification-receipt", type=Path, required=True)
    execute.add_argument("--attempt", type=int, choices=[1, 2], default=1)
    execute.add_argument(
        "--kernel-id",
        type=str,
        required=True,
        help="Explicit Kaggle kernel slug, version, and URL",
    )
    execute.set_defaults(func=command_execute_all)

    det = subparsers.add_parser("verify-determinism")
    det.set_defaults(func=command_verify_determinism)

    return parser.parse_args()


if __name__ == "__main__":
    parsed = parse_args()
    parsed.func(parsed)
