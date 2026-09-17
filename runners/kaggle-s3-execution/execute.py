#!/usr/bin/env python3
"""Fail-closed runner script for BatteryML Protocol Robustness S3 on Kaggle CPU host.

Performs:
- Unique discovery of driver, ratification receipt, and raw dataset
- Deterministic listing and SHA-256 fingerprinting of the mounted control dataset
- Environment variable configuration under the volmax1 namespace
- Isolated subprocess invocation of s3_kaggle_driver.py execute-all
- Streaming stdout logs with blindness protection
- Post-run execution report with control mount listing for external identity binding
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


KERNEL_SLUG = "volmax1/batteryml-protocol-robustness-s3-run"
KERNEL_URL = f"https://www.kaggle.com/code/{KERNEL_SLUG}"
CONTROL_DATASET_SLUG = "volmax1/batteryml-protocol-robustness-s3-controls"

EXPECTED_DRIVER_SHA256 = "e2d6f83be4139ff99b23be1b61ce0e22b208b5b742c618899761077402e49b36"
EXPECTED_PREREG_SHA256 = "5c39c1a31fd67299f62828f2ab0b48e982f159b74532ae7b29140ff96fce1350"
EXPECTED_SPLIT_MANIFEST_SHA256 = "cf9c269a93053e64ecf9200e0ee704fb0c32d2787f721fc24f0cb711cdc33895"


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def deterministic_listing(root: Path) -> tuple[str, str]:
    """Return canonical SHA-256 listing text and its SHA-256."""
    rows: list[str] = []
    for path in sorted(root.rglob("*"), key=lambda item: item.relative_to(root).as_posix()):
        relative = path.relative_to(root).as_posix()
        if path.is_symlink():
            raise RuntimeError(f"Symlink is not admissible in control dataset: {relative}")
        if path.is_file():
            rows.append(f"{sha256_file(path)}  {relative}\n")
    if not rows:
        raise RuntimeError("Control dataset contains no regular files")
    text = "".join(rows)
    return text, hashlib.sha256(text.encode("utf-8")).hexdigest()


def read_key_value_receipt(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if "=" in line:
            key, value = line.split("=", 1)
            values[key.strip()] = value.strip()
    return values


def validate_control_mount(
    control_root: Path,
    receipt_path: Path,
) -> tuple[str, dict[str, Any]]:
    driver = control_root / "runners" / "s3_kaggle_driver.py"
    if not driver.is_file():
        driver = control_root / "s3_kaggle_driver.py"
    prereg = control_root / "PREREGISTRATION.md"
    split_manifest = control_root / "s3-split-manifest.csv"

    expected_files = {
        driver: EXPECTED_DRIVER_SHA256,
        prereg: EXPECTED_PREREG_SHA256,
        split_manifest: EXPECTED_SPLIT_MANIFEST_SHA256,
    }
    for path, expected in expected_files.items():
        if not path.is_file():
            raise FileNotFoundError(f"Required file missing from control mount: {path}")
        actual = sha256_file(path)
        if actual != expected:
            raise RuntimeError(f"Frozen input SHA-256 mismatch: {path} ({actual} != {expected})")

    receipt = read_key_value_receipt(receipt_path)
    required_receipt = {
        "status": "RATIFIED",
        "instance": "batteryml-protocol-robustness-s3",
        "prereg_sha256": EXPECTED_PREREG_SHA256,
        "driver_sha256": EXPECTED_DRIVER_SHA256,
        "split_manifest_sha256": EXPECTED_SPLIT_MANIFEST_SHA256,
    }
    for key, expected in required_receipt.items():
        if receipt.get(key) != expected:
            raise RuntimeError(f"Ratification receipt {key} mismatch: {receipt.get(key)} != {expected}")
    for key in (
        "operator",
        "authorized_at",
        "operator_verbatim_statement",
        "operator_statement_location",
    ):
        if not receipt.get(key, "").strip():
            raise RuntimeError(f"Ratification receipt lacks {key}")

    listing_text, listing_sha = deterministic_listing(control_root)
    mount_receipt = {
        "configured_slug": CONTROL_DATASET_SLUG,
        "mount_path": str(control_root),
        "version": None,
        "version_binding_status": "POST_RUN_API_BINDING_PENDING",
        "listing_sha256": listing_sha,
        "file_count": len(listing_text.splitlines()),
    }
    return listing_text, mount_receipt


def main() -> None:
    print(f"[{utcnow()}] [S3-EXECUTE] Initializing fail-closed S3 runner on Kaggle host...")
    input_root = Path("/kaggle/input")
    working = Path("/kaggle/working")
    report_path = working / "EXECUTION_REPORT.json"

    # 1. Discover mounted driver (fail-closed: exactly 1 expected)
    driver_candidates = sorted(input_root.rglob("s3_kaggle_driver.py"))
    if len(driver_candidates) != 1:
        # If duplicated in root and runners/ subfolder of the same control dataset, resolve to root
        unique_parents = {p.parent if p.parent.name != "runners" else p.parent.parent for p in driver_candidates}
        if len(unique_parents) != 1:
            raise RuntimeError(f"Expected driver in exactly one control mount root, found: {driver_candidates!r}")
        control_root = list(unique_parents)[0]
        driver = control_root / "runners" / "s3_kaggle_driver.py"
        if not driver.is_file():
            driver = control_root / "s3_kaggle_driver.py"
    else:
        driver = driver_candidates[0]
        control_root = driver.parent if driver.parent.name != "runners" else driver.parent.parent

    print(f"[{utcnow()}] [S3-EXECUTE] Found driver: {driver}")
    print(f"[{utcnow()}] [S3-EXECUTE] Control root: {control_root}")

    # 2. Discover ratification receipt (fail-closed: exactly 1 expected)
    receipt_candidates = sorted(input_root.rglob("ratification-receipt.txt"))
    if len(receipt_candidates) != 1:
        raise RuntimeError(
            f"Expected exactly one ratification receipt (ratification-receipt.txt), found: {len(receipt_candidates)}"
        )
    receipt_path = receipt_candidates[0]
    if receipt_path.parent != control_root and receipt_path.parent != control_root / "receipts":
        raise RuntimeError(f"Ratification receipt is not at control mount root or receipts/: {receipt_path}")
    print(f"[{utcnow()}] [S3-EXECUTE] Found ratification receipt: {receipt_path}")

    # 3. Discover raw MATR batch data (fail-closed: exactly 1 expected)
    raw_candidates = sorted(input_root.rglob("2017-05-12_batchdata_updated_struct_errorcorrect.mat"))
    if len(raw_candidates) != 1:
        raise RuntimeError(f"Expected exactly one MATR batch1 file, found: {len(raw_candidates)}")
    raw_root = raw_candidates[0].parent
    print(f"[{utcnow()}] [S3-EXECUTE] Found raw dataset root: {raw_root}")

    # 4. Validate control mount and compute deterministic listing
    listing_text, control_mount = validate_control_mount(control_root, receipt_path)
    listing_path = working / "control-dataset-files.sha256"
    listing_path.write_text(listing_text, encoding="utf-8")
    print(f"[{utcnow()}] [S3-EXECUTE] Control dataset verified: {control_mount['file_count']} files, listing SHA: {control_mount['listing_sha256']}")

    # 5. Clean working namespace verification
    for forbidden in ["s3-artifact", "s3-processed-matr", "s3-site-packages"]:
        p = working / forbidden
        if p.exists():
            raise RuntimeError(f"Pre-existing namespace path found: {p}")

    cmd = [
        sys.executable,
        str(driver),
        "execute-all",
        "--ratification-receipt",
        str(receipt_path),
        "--attempt",
        "1",
        "--kernel-id",
        KERNEL_SLUG,
    ]
    report: dict[str, Any] = {
        "runner_preflight_utc": utcnow(),
        "status": "PREFLIGHT_PASS_API_BINDING_PENDING",
        "scientific_run_executed": False,
        "driver_process_started": False,
        "post_run_api_binding_required": True,
        "kernel_binding": {
            "configured_slug": KERNEL_SLUG,
            "configured_url": KERNEL_URL,
            "version": None,
            "status": "POST_RUN_API_BINDING_PENDING",
        },
        "control_dataset_mount": control_mount,
        "control_dataset_listing": listing_text,
        "control_dataset_listing_sha256": control_mount["listing_sha256"],
        "control_dataset_listing_path": str(listing_path),
        "ratification_receipt_path": str(receipt_path),
        "ratification_receipt_sha256": sha256_file(receipt_path),
        "runner_sha256": sha256_file(Path(__file__).resolve()),
        "governing": {
            "preregistration_sha256": EXPECTED_PREREG_SHA256,
            "split_manifest_sha256": EXPECTED_SPLIT_MANIFEST_SHA256,
        },
        "command": cmd,
    }
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    print(f"[{utcnow()}] [S3-EXECUTE] Preflight PASS; spawning scientific driver: {' '.join(cmd)}")
    sys.stdout.flush()
    report["driver_process_started"] = True
    report["runner_start_utc"] = utcnow()
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    process = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
        env={
            **dict(os.environ),
            "S3_INPUT_ROOT": str(control_root),
            "S3_RAW_ROOT": str(raw_root),
            "S3_WORKING_ROOT": str(working),
        },
    )

    assert process.stdout is not None
    for line in iter(process.stdout.readline, ""):
        print(line, end="", flush=True)
    process.stdout.close()
    returncode = process.wait()
    end_time = utcnow()

    print(f"[{utcnow()}] [S3-EXECUTE] Driver process finished with return code: {returncode}")

    report["runner_end_utc"] = end_time
    report["exit_code"] = returncode
    report["status"] = (
        "SCIENTIFIC_EXECUTION_COMPLETE_API_BINDING_PENDING"
        if returncode == 0
        else "DRIVER_FAILED_API_BINDING_PENDING"
    )

    artifact_dir = working / "s3-artifact"
    if artifact_dir.is_dir():
        for name in ["completion-receipt.json", "adjudication_candidate.json", "attempt-ledger.json"]:
            fpath = artifact_dir / name
            if fpath.is_file():
                try:
                    report[name.replace(".json", "").replace("-", "_")] = json.loads(fpath.read_text(encoding="utf-8"))
                except Exception as e:
                    report[name] = f"Error reading {name}: {e}"

        manifest_path = artifact_dir / "artifact-files.sha256"
        if manifest_path.is_file():
            report["artifact_manifest_content"] = manifest_path.read_text(encoding="utf-8")

    if returncode == 0 and (artifact_dir / "completion-receipt.json").is_file():
        report["scientific_run_executed"] = True

    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"[{utcnow()}] [S3-EXECUTE] Wrote EXECUTION_REPORT.json to /kaggle/working.")
    sys.stdout.flush()

    if returncode != 0:
        sys.exit(returncode)


if __name__ == "__main__":
    main()
