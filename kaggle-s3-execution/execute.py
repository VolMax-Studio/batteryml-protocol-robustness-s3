#!/usr/bin/env python3
"""Runner script for BatteryML Protocol Robustness S3 on Kaggle CPU host."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


KERNEL_SLUG = "volmax/batteryml-protocol-robustness-s3-run"


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def main() -> None:
    print(f"[{utcnow()}] [S3-EXECUTE] Initializing S3 Runner on Kaggle host...")

    # 1. Discover mounted driver
    driver_candidates = sorted(Path("/kaggle/input").rglob("s3_kaggle_driver.py"))
    if not driver_candidates:
        raise RuntimeError("s3_kaggle_driver.py not found in /kaggle/input")
    driver = driver_candidates[0]
    control_root = driver.parent
    if driver.parent.name == "runners":
        control_root = driver.parent.parent
    print(f"[{utcnow()}] [S3-EXECUTE] Found driver: {driver}")
    print(f"[{utcnow()}] [S3-EXECUTE] Control root: {control_root}")

    # 2. Discover ratification receipt
    receipt_candidates = sorted(Path("/kaggle/input").rglob("ratification-receipt.txt"))
    if not receipt_candidates:
        raise RuntimeError("Ratification receipt (ratification-receipt.txt) not found in /kaggle/input")
    receipt_path = receipt_candidates[0]
    print(f"[{utcnow()}] [S3-EXECUTE] Found ratification receipt: {receipt_path}")

    # 3. Discover raw MATR data
    raw_candidates = sorted(Path("/kaggle/input").rglob("2017-05-12_batchdata_updated_struct_errorcorrect.mat"))
    if not raw_candidates:
        raise RuntimeError("Raw MATR dataset not found in /kaggle/input")
    raw_root = raw_candidates[0].parent
    print(f"[{utcnow()}] [S3-EXECUTE] Found raw dataset root: {raw_root}")

    # 4. Set environment variables
    os.environ["S3_INPUT_ROOT"] = str(control_root)
    os.environ["S3_RAW_ROOT"] = str(raw_root)
    os.environ["S3_WORKING_ROOT"] = "/kaggle/working"
    os.environ["KAGGLE_KERNEL_RUN_TYPE"] = "kaggle-cpu-kernel"
    os.environ["KAGGLE_URL"] = f"https://www.kaggle.com/code/{KERNEL_SLUG}"

    # 5. Clean working namespace verification
    working = Path("/kaggle/working")
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
    print(f"[{utcnow()}] [S3-EXECUTE] Spawning: {' '.join(cmd)}")
    sys.stdout.flush()

    start_time = utcnow()
    process = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )

    collected_output = []
    assert process.stdout is not None
    for line in iter(process.stdout.readline, ""):
        print(line, end="", flush=True)
        collected_output.append(line)
    process.stdout.close()
    returncode = process.wait()
    end_time = utcnow()

    print(f"[{utcnow()}] [S3-EXECUTE] Process finished with return code: {returncode}")

    artifact_dir = working / "s3-artifact"
    report = {
        "runner_start_utc": start_time,
        "runner_end_utc": end_time,
        "kernel_id": KERNEL_SLUG,
        "command": cmd,
        "exit_code": returncode,
        "status": "PASS" if returncode == 0 else "FAIL",
    }

    if returncode == 0 and artifact_dir.is_dir():
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

    (working / "EXECUTION_REPORT.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(f"[{utcnow()}] [S3-EXECUTE] Wrote EXECUTION_REPORT.json to /kaggle/working.")
    sys.stdout.flush()

    if returncode != 0:
        sys.exit(returncode)


if __name__ == "__main__":
    main()
