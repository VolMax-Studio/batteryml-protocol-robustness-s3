# S3 Study Status Ledger

- **Instance**: `batteryml-protocol-robustness-s3`
- **Current State**: `DESIGN_V4_FROZEN_CANDIDATE`
- **Preceding Study**: `batteryml-protocol-generalization-s2.1-kaggle` (RATIFIED / CLOSED @ `dbb142e77901cb5ee245c98af3b42e3d407c32a5`)
- **Scientific Execution Authorized**: `false`

---

## State Transition History

| Timestamp (UTC) | State | Event / Transition Description |
| :--- | :--- | :--- |
| 2026-09-17 19:10 | `DESIGN_V1_INITIATED` | Initial S3 multi-split design drafted post-S2.1 |
| 2026-09-17 19:45 | `DESIGN_V2_AUDITED` | Claude Gate review: F-1 through F-5 raised |
| 2026-09-17 20:15 | `DESIGN_V3_CONVERGED` | Astra/Claude consensus: 2 gating controls, exact seed, $K=64$ derivation |
| 2026-09-17 20:45 | `PRECOMMITMENT_VERIFIED` | 2 independent implementations confirm rank hashes and membership commitment |
| 2026-09-17 21:25 | `DESIGN_V4_FROZEN_CANDIDATE` | Consolidate v4 self-contained preregistration; awaiting Claude Gate final freeze verdict & Operator ratification |

---

## Governing Commitments

- **Primary Space Count $C(0, 42, 20)$**: `185471`
- **Reference S2.1 B Rank**: `169301`
- **Sampled Ranks Count ($K$)**: `64`
- **Draw Order Rank Hash (SHA-256)**: `1d84b7bf864945a26ec0a5d2feec754b6ed6b4bf50b9f4e5b02bc45720b0ff02`
- **Ascending Rank Hash (SHA-256)**: `0f2de17c98e615023ef5966630fd93962382c4566c36a43b0d386bd0a8dbfc40`
- **Test Membership Commitment Hash (SHA-256)**: `53a157ecd49c0a238cd5028c6ab840431a7ecb600b067290ee51645820cb5ada` (16,176 B)
- **Sampler Manifest Hash (SHA-256)**: `cf9c269a93053e64ecf9200e0ee704fb0c32d2787f721fc24f0cb711cdc33895` (108,942 B, 5,313 lines)
