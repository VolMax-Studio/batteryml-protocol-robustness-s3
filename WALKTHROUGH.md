# Walkthrough: S3 Multi-Split Execution, Verification & Post-Run Binding

Study **`batteryml-protocol-robustness-s3`** has completed platform execution and post-run custody binding.
Attempt 1 on Kaggle CPU executed to full completion without error. All artifacts were downloaded, verified against the frozen precommitments, and independently recomputed from raw per-cell predictions.

---

## 1. Execution Summary (Attempt 1)

| Parameter | Value | Reference / Evidence |
| :--- | :--- | :--- |
| **Kaggle Kernel** | `volmax1/batteryml-protocol-robustness-s3-run` | Kernel ID `134781615`, Version 1 |
| **Control Dataset** | `volmax1/batteryml-protocol-robustness-s3-controls` | Version 1 (`matching_versions: [1]`, `bound_version: 1`) |
| **Dispatch / Start UTC** | `2026-09-17T21:42:39Z` | Verified via Kaggle API & `attempt-ledger.json` |
| **Completion UTC** | `2026-09-18T04:06:21Z` | Verified via Kaggle API & `completion-receipt.json` |
| **Total Duration** | **6h 23m 42s** | Well within the 12-hour batch session limit |
| **Exit Code / Disposition** | `0` / `GOVERNING_COMPLETE` | `EXECUTION_REPORT.json` |
| **Fits Executed** | **264 / 264** | Split A (4), Ref B (4), 64 Sampled Splits (256) |

---

## 2. Gating Controls (Split A & Ref B)

Both mandatory gating controls passed within strict numerical tolerance:

| Gate | Model | Measured RMSE | Measured MAE | Reference Baseline (S2.1) | Delta | Status |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **Gate 1 (Split A Positive Control)** | `variance` | 136.1296 | 109.0649 | RMSE: 136.1296, MAE: 109.0649 | $< 10^{-7}$ | **PASS** |
| | `ridge` | 115.7892 | 80.4132 | RMSE: 115.7892, MAE: 80.4132 | $< 10^{-7}$ | **PASS** |
| | `xgb` | 333.6646 | 155.5015 | RMSE: 333.6646, MAE: 155.5015 | $< 10^{-7}$ | **PASS** |
| | `dummy` | 398.8228 | 238.9885 | Reference Baseline | — | **PASS** |
| **Gate 2 (Ref Split B Reference)** | `variance` | 133.4759 | 109.7309 | RMSE: 133.4759, MAE: 109.7309 | $< 10^{-8}$ | **PASS** |
| | `ridge` | 138.5033 | 83.3048 | RMSE: 138.5033, MAE: 83.3048 | $< 10^{-8}$ | **PASS** |
| | `xgb` | 345.9461 | 212.0767 | RMSE: 345.9461, MAE: 212.0767 | $< 10^{-8}$ | **PASS** |
| | `dummy` | 426.1157 | 231.0958 | Reference Baseline | — | **PASS** |

---

## 3. Governing Identity Verification (Gate B-1 Resolution)

Machine verification was performed via [`verifiers/verify_s3_execution_identity.py`](file:///home/volmax-studio/volmax-projects/iot2/batteryml-protocol-robustness-s3/verifiers/verify_s3_execution_identity.py):
- **Partition Count**: Exactly 64 unique sampled splits (`draw_index` $0 \dots 63$).
- **Rank Bounds**: Minimum rank $1,666$, Maximum rank $184,309$ (all strictly within DP space count $185,471$).
- **Draw Order Rank Hash**: `1d84b7bf864945a26ec0a5d2feec754b6ed6b4bf50b9f4e5b02bc45720b0ff02` (**MATCH**)
- **Ascending Rank Hash**: `0f2de17c98e615023ef5966630fd93962382c4566c36a43b0d386bd0a8dbfc40` (**MATCH**)
- **Membership Commitment Hash**: `53a157ecd49c0a238cd5028c6ab840431a7ecb600b067290ee51645820cb5ada` (**MATCH**)
- **Row-for-row match**: Byte-identical with `s3-test-membership-commitment.csv`.

---

## 4. Independent Recomputation & Adjudication Results

All 264 fits were independently evaluated from raw `per-cell-predictions.csv` files with verification of both RMSE and MAE against host receipts:

### **Adjudication Category: `MODEL_SPECIFIC`**

```text
Adjudication Decision: MODEL_SPECIFIC
Materially Prevalent Degraded Models: ['ridge']
Positive Systematic Models: ['ridge']
Model Ranking Order Change Rate: 70.3125% (45 of 64 splits differed from Split A ranking)
Dummy Composition Sensitivity Flag: NOT ACTIVATED (p_abs = 46.88% < 50%)
```

### Model Performance Metrics Across $K=64$ Disjoint Splits

| Model | $p_{\text{pos}}$ ($D \ge +0.10$) | $p_{\text{abs}}$ ($\|D\| \ge 0.10$) | $p_{\text{neg}}$ ($D \le -0.10$) | Median $D^{\text{RMSE}}$ | IQR $[Q_{0.25}, Q_{0.75}]$ | Tail $[Q_{0.05}, Q_{0.95}]$ | Preregistered Finding |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :--- |
| **`ridge`** | **85.94%** | **90.62%** | 4.69% | **+35.83%** | $[+22.08\%, +91.69\%]$ | $[-4.64\%, +106.02\%]$ | **Materially Prevalent Degraded** |
| **`variance`** | 29.69% | 31.25% | 1.56% | **+6.02%** | $[+1.05\%, +10.62\%]$ | $[-4.03\%, +24.82\%]$ | **Sub-threshold (Not prevalent)** |
| **`xgb`** | 28.12% | 43.75% | 15.62% | **+1.63%** | $[-6.73\%, +16.06\%]$ | $[-13.24\%, +24.72\%]$ | **Sub-threshold (Not prevalent)** |
| **`dummy`** | — | 46.88% | — | +8.94% | $[+7.25\%, +20.71\%]$ | $[+4.78\%, +24.11\%]$ | Flag Not Activated ($< 50\%$) |

---

## 5. Scientific Claim Boundaries & Interpretation

1. **Model-Specific Sensitivity**:
   - Under the preregistered sample of 64 minimum-cost protocol-disjoint `primary83` partitions, the observed degradation is **model-specific**.
   - Ridge regression showed material RMSE increases ($\ge 10\%$) in **90.6%** of sampled splits ($p_{\text{abs}} = 0.906$) and positive increases in **85.9%** ($p_{\text{pos}} = 0.859$), with a median relative RMSE change of approximately **+35.8%**.
   - The Severson Variance Model and XGBoost did not cross the preregistered material-prevalence threshold ($p_{\text{abs}} < 0.50$, observed $31.25\%$ and $43.75\%$), with positive increases occurring in under 30% of splits ($p_{\text{pos}} = 29.69\%$ and $28.12\%$).

2. **Benchmark Ranking Sensitivity**:
   - The relative ordering of the three evaluated models differed from the published BatteryML Split A ranking in **45 of 64 preregistered protocol-disjoint partitions (70.3%)**.
   - These findings show that the relative ordering of the three evaluated models is sensitive under protocol-disjoint evaluation, where protocol holdout and test-composition changes occur together.

3. **Composition Diagnostics**:
   - The preregistered dummy composition-sensitivity flag was not activated ($p_{\text{abs}}(\text{dummy}) = 46.9\% < 50\%$).
   - However, because dummy RMSE shifted with a median of $+8.9\%$, cell composition effects are not ruled out and may contribute alongside protocol holdout shifts.

4. **Scope Limitations**:
   - This finding applies strictly to the pinned BatteryML MATR1 benchmark under protocol-disjoint primary83 partitions.
   - It does not establish universal degradation across all machine learning models, data leakage, misconduct, a pure causal protocol effect, or direct transferability to field BESS/Battery Passport operation.

---

## 6. Binding Receipts & Integrity

- **Control Dataset Version Binding (F-1)**: Kaggle published dataset `volmax1/batteryml-protocol-robustness-s3-controls` candidate version 1 matches runtime listing `9da5f90c...` byte-for-byte (`bound_version: 1`).
- **Post-Run Binding Receipt**: [`receipts/post-run-binding-receipt.json`](file:///home/volmax-studio/volmax-projects/iot2/batteryml-protocol-robustness-s3/receipts/post-run-binding-receipt.json) (SHA-256: `1ad8fdc4...`)
- **Governing Adjudication Record**: [`receipts/governing-adjudication.json`](file:///home/volmax-studio/volmax-projects/iot2/batteryml-protocol-robustness-s3/receipts/governing-adjudication.json) (SHA-256: `36df005f...`)
- **Public Evidence Manifest**: 1,130 public evidence files verified (`public-evidence-files.sha256`).
- **Checkpoint Manifest**: 264 model checkpoints hashed (`checkpoint-files.sha256`).

---

## 7. Formal Verdict Ratification (Study Closure)

Operator [L3] issued formal Verdict Ratification at `2026-09-18T17:15:14+02:00`:
- **Ratified Scientific Verdict**: **`MODEL_SPECIFIC`**
- **Governing Evidence Commit**: [`9a0ad9c`](https://github.com/VolMax-Studio/batteryml-protocol-robustness-s3/commit/9a0ad9c)
- **Verdict Ratification Receipt**: [`receipts/verdict-ratification-receipt.txt`](file:///home/volmax-studio/volmax-projects/iot2/batteryml-protocol-robustness-s3/receipts/verdict-ratification-receipt.txt) / [`receipts/verdict-ratification-receipt.json`](file:///home/volmax-studio/volmax-projects/iot2/batteryml-protocol-robustness-s3/receipts/verdict-ratification-receipt.json)
- **Study Status**: **`RATIFIED / CLOSED`**

