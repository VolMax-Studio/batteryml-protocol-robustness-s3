#!/usr/bin/env python3
"""Tests for S3 Kaggle Driver, Runner, and Governing Bindings."""

import hashlib
import json
import os
import py_compile
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
RUNNERS_DIR = ROOT / "runners"
DRIVER_PATH = RUNNERS_DIR / "s3_kaggle_driver.py"
RUNNER_REPO_PATH = RUNNERS_DIR / "kaggle-s3-execution" / "execute.py"
RUNNER_ROOT_PATH = ROOT / "kaggle-s3-execution" / "execute.py"


def test_driver_compiles():
    """Verify s3_kaggle_driver.py compiles without syntax errors."""
    assert DRIVER_PATH.is_file()
    py_compile.compile(str(DRIVER_PATH), doraise=True)


def test_runner_compiles():
    """Verify execute.py compiles without syntax errors in both locations."""
    assert RUNNER_REPO_PATH.is_file()
    py_compile.compile(str(RUNNER_REPO_PATH), doraise=True)
    assert RUNNER_ROOT_PATH.is_file()
    py_compile.compile(str(RUNNER_ROOT_PATH), doraise=True)


def test_governing_commitments():
    """Verify DP space count, reference rank, rank hashes, membership commitment, and manifest hash."""
    import sys
    sys.path.insert(0, str(ROOT))
    sys.path.insert(0, str(RUNNERS_DIR))
    
    os.environ["S3_INPUT_ROOT"] = str(ROOT)
    from s3_kaggle_driver import verify_governing_commitments

    commitments = verify_governing_commitments()
    assert commitments["dp_count"] == 185471
    assert commitments["s2_reference_rank"] == 169301
    assert commitments["draw_order_hash"] == "1d84b7bf864945a26ec0a5d2feec754b6ed6b4bf50b9f4e5b02bc45720b0ff02"
    assert commitments["ascending_hash"] == "0f2de17c98e615023ef5966630fd93962382c4566c36a43b0d386bd0a8dbfc40"
    assert commitments["membership_commitment_hash"] == "53a157ecd49c0a238cd5028c6ab840431a7ecb600b067290ee51645820cb5ada"
    assert commitments["split_manifest_hash"] == "cf9c269a93053e64ecf9200e0ee704fb0c32d2787f721fc24f0cb711cdc33895"
    assert commitments["governing_commitments_verified"] is True


def test_sampled_splits_ascending_rank_and_membership():
    """Verify that sampled splits load in ascending split_rank order while preserving draw_index."""
    import sys
    sys.path.insert(0, str(ROOT))
    sys.path.insert(0, str(RUNNERS_DIR))
    
    os.environ["S3_INPUT_ROOT"] = str(ROOT)
    from s3_kaggle_driver import load_all_sampled_splits

    splits = load_all_sampled_splits()
    assert len(splits) == 64

    # Verify strictly ascending split_rank
    ranks = [s["split_rank"] for s in splits]
    assert ranks == sorted(ranks)
    assert len(set(ranks)) == 64

    # Verify positions are 1..64
    positions = [s["execution_position"] for s in splits]
    assert positions == list(range(1, 65))

    # Verify each split matches s3-test-membership-commitment.csv by draw_index
    mem_map = {}
    with open(ROOT / "s3-test-membership-commitment.csv", "r", encoding="utf-8") as f:
        for line in f:
            d_idx, rk, cells_pipe = line.strip().split(",")
            mem_map[int(d_idx)] = (int(rk), sorted(cells_pipe.split("|")))

    for s in splits:
        d = s["draw_index"]
        exp_rank, exp_cells = mem_map[d]
        assert s["split_rank"] == exp_rank
        assert sorted(s["test"]) == exp_cells
        assert len(s["train"]) == 41
        assert len(s["test"]) == 42


def test_read_receipt_validation():
    """Verify that read_receipt properly loads valid receipts and rejects invalid/incomplete receipts."""
    import sys
    sys.path.insert(0, str(ROOT))
    sys.path.insert(0, str(RUNNERS_DIR))
    
    os.environ["S3_INPUT_ROOT"] = str(ROOT)
    from s3_kaggle_driver import read_receipt

    prereg_sha = hashlib.sha256((ROOT / "PREREGISTRATION.md").read_bytes()).hexdigest()
    driver_sha = hashlib.sha256(DRIVER_PATH.read_bytes()).hexdigest()
    split_manifest_sha = hashlib.sha256((ROOT / "s3-split-manifest.csv").read_bytes()).hexdigest()
    mem_commitment_sha = hashlib.sha256((ROOT / "s3-test-membership-commitment.csv").read_bytes()).hexdigest()

    valid_content = f"""status=RATIFIED
instance=batteryml-protocol-robustness-s3
governing_commit=0958e89a0e994ed9923da26e04e1f4bfb956ab7f
prereg_sha256={prereg_sha}
driver_sha256={driver_sha}
split_manifest_sha256={split_manifest_sha}
membership_commitment_sha256={mem_commitment_sha}
operator=Ivan Nestorov, Operator / Final Ratifier
authorized_at=2026-09-17T21:48:29+02:00
operator_verbatim_statement=OPERATOR [L3] SCIENTIFIC EXECUTION AUTHORIZATION
operator_statement_location=antigravity-conversation-15abadc7-f175-429d-ba47-9d1ff85d1b74
"""
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False) as tf:
        tf.write(valid_content)
        tf_path = Path(tf.name)

    try:
        vals = read_receipt(tf_path)
        assert vals["status"] == "RATIFIED"
        assert vals["instance"] == "batteryml-protocol-robustness-s3"
        assert vals["prereg_sha256"] == prereg_sha
        assert vals["driver_sha256"] == driver_sha
    finally:
        tf_path.unlink(missing_ok=True)

    # Negative test: incomplete receipt raises RuntimeError
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False) as tf:
        tf.write("status=RATIFIED\ninstance=batteryml-protocol-robustness-s3\n")
        bad_path = Path(tf.name)

    try:
        with pytest.raises(RuntimeError, match="Ratification receipt fields incomplete"):
            read_receipt(bad_path)
    finally:
        bad_path.unlink(missing_ok=True)
