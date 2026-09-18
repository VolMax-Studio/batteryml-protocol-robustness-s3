#!/usr/bin/env python3
"""
Update Zenodo metadata description for deposition 22834252 with calibrated wording.
Does NOT change the DOI or touch any files.
Includes robust retry loop for transient network/DNS blips.
"""

import os
import sys
import time
import requests
from pathlib import Path

ZENODO_API = "https://zenodo.org/api"
DEP_ID = 22834252

def get_token():
    token_path = Path(os.path.expanduser("~/.zenodo_token"))
    if not token_path.exists():
        sys.exit(f"ABORT: Token file not found at {token_path}")
    token = token_path.read_text().splitlines()[0].strip()
    return token

def request_with_retry(method, url, **kwargs):
    max_retries = 6
    for attempt in range(1, max_retries + 1):
        try:
            r = requests.request(method, url, **kwargs)
            return r
        except Exception as e:
            print(f"   [Retry {attempt}/{max_retries}] Network error: {e}")
            if attempt == max_retries:
                raise
            time.sleep(3)

def main():
    token = get_token()
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }

    # 1. Unlock deposition for editing
    print(f"1. Unlocking deposition {DEP_ID} for metadata editing...")
    r = request_with_retry("POST", f"{ZENODO_API}/deposit/depositions/{DEP_ID}/actions/edit", headers=headers, timeout=30)
    print(f"   Unlock response status: {r.status_code}")

    description_html = (
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
        "The relative ordering of Variance and Ridge differed from Split A in 45 of 64 partitions (70.3%).</li>"
        "<li><strong>Outlier diagnostic:</strong> The preregistered no-refit b2c1 diagnostic showed substantially larger Ridge leverage (median J=2.19) than for Variance and XGBoost, which were near zero. This diagnostic is not a causal decomposition of the split effect.</li>"
        "</ul>"
        "<p><strong>Lineage & Provenance:</strong></p>"
        "<ul>"
        "<li>GitHub Repository: <a href=\"https://github.com/VolMax-Studio/batteryml-protocol-robustness-s3\">VolMax-Studio/batteryml-protocol-robustness-s3</a> (Release v1.0.0 / commit <code>4bdf33e</code>)</li>"
        "<li>Preceding study S2.1: <a href=\"https://github.com/VolMax-Studio/batteryml-protocol-generalization-s2-kaggle\">batteryml-protocol-generalization-s2-kaggle</a> (commit <code>dbb142e</code>)</li>"
        "<li>Evaluated benchmark: Microsoft BatteryML (commit <code>2861ae3b</code>), MIT License. MATR1 data: Severson et al. (2019), CC BY 4.0.</li>"
        "</ul>"
    )

    metadata = {
        "metadata": {
            "title": "Preregistered Robustness Evaluation of BatteryML MATR1 Under Minimum-Cost Protocol-Disjoint Partitions",
            "upload_type": "dataset",
            "description": description_html,
            "creators": [
                {
                    "name": "Nestorov, Ivan",
                    "affiliation": "VolMax Studio Lab",
                    "orcid": "0009-0006-7940-9539"
                }
            ],
            "access_right": "open",
            "license": "CC-BY-4.0",
            "version": "1.0.0",
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
    }

    # 2. Update deposition metadata
    print("2. Updating Zenodo deposition metadata...")
    r = request_with_retry(
        "PUT",
        f"{ZENODO_API}/deposit/depositions/{DEP_ID}",
        headers=headers,
        json=metadata,
        timeout=30
    )
    if r.status_code != 200:
        sys.exit(f"ABORT: Failed to update metadata: {r.status_code} - {r.text}")
    print("   Metadata updated successfully in draft.")

    # 3. Publish deposition changes
    print("3. Publishing updated deposition...")
    r = request_with_retry(
        "POST",
        f"{ZENODO_API}/deposit/depositions/{DEP_ID}/actions/publish",
        headers=headers,
        timeout=30
    )
    if r.status_code not in [200, 201, 202]:
        sys.exit(f"ABORT: Failed to publish metadata changes: {r.status_code} - {r.text}")

    pub = r.json()
    doi = pub["doi"]
    print(f"\nSUCCESS: Metadata published to Zenodo! DOI remains: {doi}")
    print(f"Record: https://zenodo.org/record/{DEP_ID}")

if __name__ == "__main__":
    main()
