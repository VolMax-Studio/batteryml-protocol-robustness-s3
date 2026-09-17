# BatteryML Protocol Robustness — S3 Multi-Split Sweep

> This repository is a separate post-S2.1 study.  
> S2.1 is closed and immutable at `dbb142e77901cb5ee245c98af3b42e3d407c32a5`.  
> S3 is non-blind by design: S2.1 results were known before S3 preregistration.

This repository is the preregistration, sampler specification, and evidence index for `batteryml-protocol-robustness-s3`, a distributional robustness study evaluating BatteryML MATR1 models across an exact-size, minimum-cost, protocol-disjoint split universe.

- **Status**: `DESIGN_V4_FROZEN_CANDIDATE`
- **Study Paradigm**: Preregistered post-S2.1 multi-split robustness sweep
- **Preceding Instance**: [`batteryml-protocol-generalization-s2.1-kaggle`](https://github.com/VolMax-Studio/batteryml-protocol-generalization-s2-kaggle) (Head: [`dbb142e`](https://github.com/VolMax-Studio/batteryml-protocol-generalization-s2-kaggle/commit/dbb142e77901cb5ee245c98af3b42e3d407c32a5))

---

## Overview & Scientific Purpose

S2.1 demonstrated that evaluating models on an exact-size protocol-disjoint split changed benchmark outcomes (+19.6% Ridge RMSE and ranking inversion), but also revealed strong sensitivity to test composition and outlier cell `b2c1`.

S3 advances from single-point evaluation to a **distributional robustness map**:
- Samples $K=64$ distinct splits uniformly without replacement from the $185,470$ candidate minimum-cost protocol-disjoint partitions.
- Evaluates 4 models (`dummy`, `variance`, `ridge`, `xgb`) across all partitions ($4 \times (64 + 2) = 264$ fits).
- Measures the empirical prevalence, direction, and magnitude of metric changes ($D^{RMSE}$, $D^{MAE}$, Skill, residual concentrations).
- Evaluates the `b2c1` outlier sensitivity axis on identical checkpoints without model refitting.
- Enforces two separate $1.0\%$ positive control gates before any sampled split is adjudicated:
  1. **BatteryML Split A baseline gate**: requires reproduction of the published benchmark within $1.0\%$.
  2. **S2.1 Reference Split B gate**: requires reproduction of the S2.1 reference result within $1.0\%$.

---

## Core Artifacts & Hashes

| Artifact | Description | Bytes / Lines | SHA-256 |
| :--- | :--- | :--- | :--- |
| [`PREREGISTRATION.md`](PREREGISTRATION.md) | Governing S3 design document | 415 lines | *Frozen candidate* |
| [`sampler_input.csv`](sampler_input.csv) | Canonical 4-column primary83 input | 83 rows, 7205 B | `ac672728d9857c417d4f51812f31b20711307f0e7ee20efacf8f38f1b3dfb42e` |
| [`s3-split-manifest.csv`](s3-split-manifest.csv) | Generated 64-split manifest | 5313 lines, 108942 B | `cf9c269a93053e64ecf9200e0ee704fb0c32d2787f721fc24f0cb711cdc33895` |
| [`s3-test-membership-commitment.csv`](s3-test-membership-commitment.csv) | Test membership pre-commitment | 64 rows, 16176 B | `53a157ecd49c0a238cd5028c6ab840431a7ecb600b067290ee51645820cb5ada` |
| [`s3-sampler-ranks.json`](s3-sampler-ranks.json) | The 64 unranked sampled ranks | 64 ranks | *Derived from seed* |
| [`receipts/session-limit-receipt.json`](receipts/session-limit-receipt.json) | Kaggle docs limit receipt & $K=64$ derivation | 2245 B | *Recorded* |
| [`receipts/kaggle-notebooks-session-limit-innertext.txt`](receipts/kaggle-notebooks-session-limit-innertext.txt) | Rendered innerText snapshot of Kaggle docs | 37573 chars, 37771 B | `d3934243cd66f8f2c37606a5afd967cfdddc1fe9ce081472b1e4b68f4acaab78` |
| [`s3_sampler.py`](s3_sampler.py) | Standalone DP sampler, unranker, & invariant verifier | 321 lines | *Deterministic* |
| [`s3_adjudication.py`](s3_adjudication.py) | Pure adjudication engine & metric calculation | 200 lines | *Deterministic* |

---

## Verification & Self-Test

Anyone can independently verify the dynamic programming counting, unranking, and invariant satisfaction:

```bash
# 1. Run standalone sampler verification:
python3 s3_sampler.py --sampler-input sampler_input.csv

# 2. Run test suite (sampler invariants & adjudication synthetic fuzzing):
python3 -m unittest discover -s tests -p "test_*.py"
```

All 11 automated tests verify:
- DP table exact count: $C(0, 42, 20) = 185,471$.
- Derived S2.1 reference rank in S3 canonical order: $169,301$.
- Exact generation of 64 ranks from seed text hash `b9b522b9...`.
- Invariant satisfaction across all 64 splits (41 train, 42 test, 0 protocol overlap, cost 20, intersection with A test == 32).
- Exhaustive coverage of the 4 adjudication categories under synthetic fuzzing.

Code: Microsoft BatteryML, MIT License.  
Data: MATR / Severson et al. (2019), CC BY 4.0.
