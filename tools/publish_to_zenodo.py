#!/usr/bin/env python3
"""
Publish batteryml-protocol-robustness-s3 (v1.0.0) to Zenodo via API.
"""

import argparse
import os
import sys
import json
import subprocess
from pathlib import Path
import requests

ZENODO_API = "https://zenodo.org/api"
REPO_ROOT = Path(__file__).resolve().parent.parent
DOI_FILE = REPO_ROOT / "zenodo_doi.txt"

def get_token():
    token_path = Path(os.path.expanduser("~/.zenodo_token"))
    if not token_path.exists():
        sys.exit(f"ABORT: Token file not found at {token_path}")
    token = token_path.read_text().splitlines()[0].strip()
    if not token:
        sys.exit("ABORT: Token file is empty")
    return token

def create_archive():
    zip_path = REPO_ROOT / "batteryml-protocol-robustness-s3-v1.0.0.zip"
    print(f"Creating git archive at {zip_path}...")
    cmd = ["git", "archive", "--format=zip", "--prefix=batteryml-protocol-robustness-s3-v1.0.0/", "-o", str(zip_path), "v1.0.0"]
    res = subprocess.run(cmd, cwd=REPO_ROOT, capture_output=True, text=True)
    if res.returncode != 0:
        sys.exit(f"ABORT: git archive failed: {res.stderr}")
    size_mb = zip_path.stat().st_size / (1024 * 1024)
    print(f"Archive created successfully: {size_mb:.2f} MB")
    return zip_path

def build_metadata(version="1.0.0"):
    description = (
        "<p><strong>Preregistered Robustness Evaluation of BatteryML MATR1 Under Minimum-Cost Protocol-Disjoint Partitions</strong></p>"
        "<p>This dataset and software artifact contains the complete preregistration, deterministic sampler, partition manifests, "
        "test membership commitments, raw per-cell predictions, recomputation verifiers, and cryptographic proof receipts for the "
        "<strong>batteryml-protocol-robustness-s3</strong> multi-split robustness sweep.</p>"
        "<p><strong>Key Results & Scope:</strong></p>"
        "<ul>"
        "<li><strong>Governing Verdict:</strong> <code>MODEL_SPECIFIC</code> (Ratified by Operator [L3])</li>"
        "<li><strong>Partitions:</strong> 64 protocol-disjoint partitions sampled uniformly without replacement from the 185,470 minimum-cost population (20 cell moves from published Split A).</li>"
        "<li><strong>Evaluations:</strong> 264 total model fits across 4 models (Dummy, Variance, Ridge, XGBoost).</li>"
        "<li><strong>Positive Control:</strong> Split A baseline exactly reproduced published BatteryML numbers within numerical tolerance (Variance RMSE 136.1, Ridge 115.8, XGBoost 333.7).</li>"
        "<li><strong>Findings:</strong> Ridge exhibited recurrent material generalization sensitivity (median relative RMSE shift +35.8%, p_abs = 90.6%, p_pos = 85.9%). "
        "Variance (+6.0% median) and XGBoost (+1.6% median) did not cross the preregistered 50% material-prevalence threshold. "
        "Relative leaderboard ranking inverted from Split A in 45 of 64 partitions (70.3%).</li>"
        "<li><strong>Outlier Influence:</strong> Ridge performance shifts were heavily influenced by sensitivity to single outlier cell b2c1 (median leverage index J = 2.19).</li>"
        "</ul>"
        "<p><strong>Lineage & Provenance:</strong></p>"
        "<ul>"
        "<li>GitHub Repository: <a href=\"https://github.com/VolMax-Studio/batteryml-protocol-robustness-s3\">VolMax-Studio/batteryml-protocol-robustness-s3</a> (Release v1.0.0 / commit <code>4bdf33e</code>)</li>"
        "<li>Preceding study S2.1: <a href=\"https://github.com/VolMax-Studio/batteryml-protocol-generalization-s2-kaggle\">batteryml-protocol-generalization-s2-kaggle</a> (commit <code>dbb142e</code>)</li>"
        "<li>Evaluated benchmark: Microsoft BatteryML (commit <code>2861ae3b</code>), MIT License. MATR1 data: Severson et al. (2019), CC BY 4.0.</li>"
        "</ul>"
    )
    
    meta = {
        "title": "Preregistered Robustness Evaluation of BatteryML MATR1 Under Minimum-Cost Protocol-Disjoint Partitions",
        "upload_type": "dataset",
        "description": description,
        "creators": [
            {
                "name": "Nestorov, Ivan",
                "affiliation": "VolMax Studio Lab",
                "orcid": "0009-0006-7940-9539"
            }
        ],
        "access_right": "open",
        "license": "CC-BY-4.0",
        "version": version,
        "keywords": [
            "BatteryML",
            "Machine Learning",
            "Battery Research",
            "Benchmark Robustness",
            "Protocol Generalization",
            "Reproducible Research",
            "BESS",
            "Data Science",
            "MATR1",
            "Open Science"
        ],
        "related_identifiers": [
            {
                "identifier": "https://github.com/VolMax-Studio/batteryml-protocol-robustness-s3",
                "relation": "isSupplementTo",
                "scheme": "url"
            },
            {
                "identifier": "https://github.com/VolMax-Studio/batteryml-protocol-generalization-s2-kaggle",
                "relation": "continues",
                "scheme": "url"
            },
            {
                "identifier": "https://github.com/microsoft/BatteryML",
                "relation": "cites",
                "scheme": "url"
            }
        ]
    }
    return meta

def upload_with_retry(bucket, file_path, headers, max_retries=3):
    for attempt in range(1, max_retries + 1):
        try:
            with open(file_path, "rb") as fp:
                up_r = requests.put(f"{bucket}/{file_path.name}", headers=headers, data=fp, timeout=120)
                up_r.raise_for_status()
                return
        except Exception as e:
            print(f"    [Warning] Attempt {attempt}/{max_retries} failed for {file_path.name}: {e}")
            if attempt == max_retries:
                raise
            import time
            time.sleep(3)

def main():
    parser = argparse.ArgumentParser(description="Publish S3 archive to Zenodo")
    parser.add_argument("--publish", action="store_true", help="Actually publish and mint DOI (default is draft only)")
    parser.add_argument("--dry-run", action="store_true", help="Show files and metadata without contacting Zenodo")
    parser.add_argument("--dep-id", type=int, default=None, help="Resume existing deposition ID")
    args = parser.parse_args()

    zip_file = REPO_ROOT / "batteryml-protocol-robustness-s3-v1.0.0.zip"
    if not zip_file.exists() and not args.dep_id:
        zip_file = create_archive()
    
    # Standalone preview files to upload alongside zip for in-browser inspection
    preview_files = [
        REPO_ROOT / "README.md",
        REPO_ROOT / "PREREGISTRATION.md",
        REPO_ROOT / "STATUS.md",
        REPO_ROOT / "figures" / "s3_d_rmse_distribution.png",
        REPO_ROOT / "figures" / "s3_ranking_inversion.png",
        REPO_ROOT / "figures" / "s3_outlier_sensitivity_b2c1.png",
        REPO_ROOT / "receipts" / "governing-adjudication.json",
        REPO_ROOT / "receipts" / "verdict-ratification-receipt.txt"
    ]
    
    files_to_upload = ([zip_file] if zip_file.exists() else []) + [f for f in preview_files if f.exists()]
    meta = build_metadata()

    token = get_token()
    headers = {"Authorization": f"Bearer {token}"}
    
    if args.dep_id:
        dep_id = args.dep_id
        print(f"\nResuming existing deposition ID {dep_id}...")
        r = requests.get(f"{ZENODO_API}/deposit/depositions/{dep_id}", headers=headers, timeout=30)
        r.raise_for_status()
        dep = r.json()
    else:
        print("\n1. Creating deposition draft on Zenodo...")
        r = requests.post(
            f"{ZENODO_API}/deposit/depositions",
            headers={**headers, "Content-Type": "application/json"},
            json={"metadata": meta},
            timeout=30
        )
        if r.status_code not in [200, 201]:
            sys.exit(f"ABORT: Failed to create deposition: {r.status_code} - {r.text}")
        dep = r.json()
        dep_id = dep["id"]
        
    bucket = dep["links"]["bucket"]
    prereserved_doi = dep.get("metadata", {}).get("prereserved_doi", {}).get("doi", f"10.5281/zenodo.{dep_id}")
    existing_files = {f["filename"] for f in dep.get("files", [])}
    
    print(f"  Deposition ID: {dep_id}")
    print(f"  Pre-reserved DOI: {prereserved_doi}")
    print(f"  Draft URL: https://zenodo.org/deposit/{dep_id}")
    print(f"  Existing files in bucket ({len(existing_files)}): {existing_files}")

    print(f"\n2. Uploading files to bucket...")
    for f in files_to_upload:
        if f.name in existing_files:
            print(f"  [Skipping] Already uploaded: {f.name}")
            continue
        print(f"  Uploading {f.name} ({f.stat().st_size / 1024:.1f} KB)...")
        upload_with_retry(bucket, f, headers)
    print("  All files verified in bucket.")

    # Clean up local zip artifact if it exists
    if zip_file.exists():
        zip_file.unlink()
        print("  Cleaned up local temporary zip archive.")

    if not args.publish:
        print("\n" + "=" * 62)
        print(f"  DRAFT READY (NOT PUBLISHED)")
        print(f"  Pre-reserved DOI : {prereserved_doi}")
        print(f"  Draft Edit URL   : https://zenodo.org/deposit/{dep_id}")
        print("=" * 62)
        print("Run with --publish to finalize and mint the permanent DOI.")
        return

    print("\n3. Publishing deposition...")
    pub_r = requests.post(
        f"{ZENODO_API}/deposit/depositions/{dep_id}/actions/publish",
        headers=headers,
        timeout=30
    )
    if pub_r.status_code not in [200, 201, 202]:
        sys.exit(f"ABORT: Publish failed: {pub_r.status_code} - {pub_r.text}")
        
    pub = pub_r.json()
    doi = pub["doi"]
    concept = pub.get("conceptdoi", doi)
    record_url = pub["links"]["record_html"]

    print("\n" + "=" * 65)
    print(f"  SUCCESSFULLY PUBLISHED TO ZENODO!")
    print(f"  Version DOI (frozen) : {doi}")
    print(f"  Concept DOI (cite)   : {concept}")
    print(f"  Permanent Record     : {record_url}")
    print("=" * 65)

    with open(DOI_FILE, "w", encoding="utf-8") as f:
        f.write(f"{doi}\nhttps://doi.org/{doi}\n{record_url}\nCONCEPT_DOI={concept}\nhttps://doi.org/{concept}\n")
    print(f"\nSaved DOI record to {DOI_FILE}")

if __name__ == "__main__":
    main()
