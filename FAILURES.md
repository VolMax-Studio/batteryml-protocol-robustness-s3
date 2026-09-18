# S3 Incident & Failure Ledger

- **Instance**: `batteryml-protocol-robustness-s3`
- **Pre-freeze Failures**: 0
- **Preflight Dispatches Attempted**: 0 / 3
- **Scientific Attempts Attempted**: 0 / 2

---

## Pre-Freeze Invariant Audits

| Audit Target | Expected | Observed | Status |
| :--- | :--- | :--- | :--- |
| Dynamic Programming Space Count | 185,471 | 185,471 | PASS |
| S2.1 Reference B Rank | 169,301 | 169,301 | PASS |
| Counter Draws Consumed | 64 | 64 | PASS |
| Modulo-bias Rejections | 0 | 0 | PASS |
| Duplicate Rank Rejections | 0 | 0 | PASS |
| Reference Rank Hits | 0 | 0 | PASS |
| Draw Order Rank Hash | `1d84b7bf...` | `1d84b7bf...` | PASS |
| Ascending Rank Hash | `0f2de17c...` | `0f2de17c...` | PASS |
| Test Membership Hash | `53a157ec...` | `53a157ec...` | PASS |
| Test Membership Byte Count | 16,176 B | 16,176 B | PASS |
| Manifest Line Count | 5,313 | 5,313 | PASS |
| Manifest Byte Count | 108,942 B | 108,942 B | PASS |
| Manifest SHA-256 | `cf9c269a...` | `cf9c269a...` | PASS |
| Split Cost Invariant (all 64) | $C=20$ | $C=20$ | PASS |
| Protocol Overlap (all 64) | 0 | 0 | PASS |
| Test Intersection with Split A (all 64) | 32 | 32 | PASS |

---

## Execution Incident Log

- **Incident INC-S3-01 (Prose Reporting Discrepancy)**:
  - *Description*: Conversational text in agent report claimed split ranks were executed "od ranga 335 do 184.815".
  - *Impact*: Blocked review gate B-1 due to potential execution of non-ratified split space.
  - *Resolution*: Machine-verified via `verifiers/verify_s3_execution_identity.py` directly against output artifacts (`split-summary.json`, `run-receipt.json`). Proved that actual execution ranks were strictly $1,666$ to $184,309$, matching the frozen `s3-sampler-ranks.json` and satisfying all governing hashes (`1d84b7bf...`, `0f2de17c...`, `53a157ec...`).
  - *Takeaway*: Conversational prose numbers are not evidence; only machine-verified receipts and reproducible verifier tools govern.
