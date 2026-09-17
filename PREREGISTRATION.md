# Preregistration: BatteryML MATR1 Protocol Generalization — S3 Multi-Split Robustness Sweep

- **Instance Name**: `batteryml-protocol-robustness-s3`
- **Repository**: `VolMax-Studio/batteryml-protocol-robustness-s3`
- **Status**: `DESIGN_V4_FROZEN_CANDIDATE`
- **Study Paradigm**: Preregistered post-S2.1 distributional robustness sweep
- **Prior Knowledge Context**: Explicitly post-S2.1 and therefore non-blind (S2.1 results, Ridge signal, and `b2c1` sensitivity behavior are known prior to S3 design)

---

## 1. Scientific Question

Does the model- and ranking-sensitivity observed in S2.1 persist across a preregistered distribution of legitimate exact-size, minimum-cost, protocol-disjoint MATR1 splits, or does it depend on the particular partition, test composition, and extreme outlier cell `b2c1`?

Specifically, across an unranked uniform sample of $K=64$ minimum-cost, exact-size, protocol-disjoint `primary83` partitions:
1. How frequently and in what direction does the test RMSE of each model change relative to the BatteryML A code split?
2. How frequently does the model performance ranking change?
3. How much of the observed change is attributable to altered test composition (diagnosed via the dummy baseline)?
4. How much does the extreme cell `b2c1` alter aggregate test metrics when evaluated without model refitting?
5. Where does the S2.1 B reference partition lie within the broader distribution?

---

## 2. Frozen Parameters Block (`PARAMS`)

```yaml
PARAMS:
  study:
    instance: batteryml-protocol-robustness-s3
    repository: VolMax-Studio/batteryml-protocol-robustness-s3
    status: DESIGN_V4_FROZEN_CANDIDATE
    post_s2_nonblind: true
    frozen_manifest_sha256: 96695e534718733469ba108ee3c1372e29351710235d5b47020f6bd9ae2ce722
    s2_public_head: dbb142e77901cb5ee245c98af3b42e3d407c32a5

  pinned_components:
    batteryml_commit: 2861ae3b8c79938c7fc8e6fe9986b799ca71c7dd
    raw_matr:
      batch1_sha256: 9d928ab978f0e3c70b31cb833a749fedd35094d01af76475d69b40aa3497f5ba
      batch2_sha256: 63ab200d09ecb237fee5ef3a5c5db76e3212e3206a0bd92f769e1427fed338b8
    source_manifest:
      file_count: 205
      sha256: 5e239025955a160586a666b3cd50deb03c0e60e8ccf316fbb111156f197a516e
    configs:
      dummy_matr_1_sha256: 1cc4c73b09412cb42a13ae2e143806f1d8a1d984bd38292a0077154071f02b2d
      variance_matr_1_sha256: ab0849c3a021273629c1a6e90c09aa29eb425fdfb17aef2376888524f6984b5b
      ridge_matr_1_sha256: ad554e8c459a85278ce125a20c179dd3ed65046d5abeab455a3738d3ca793a54
      xgb_matr_1_sha256: ce3e35629429b988426d0a0b9da867e7c4411a949715dad61597b5684483a0f7
    offline_wheels:
      addict_2_4_0_sha256: 249bb56bbfd3cdc2a004ea0ff4c2b6ddc84d53bc2194761636eb314d5cfa5dfc
      fire_0_7_1_sha256: e43fd8a5033a9001e7e2973bab96070694b9f12f2e0ecf96d4683971b5ab1882
    base_pip_freeze:
      lines: 872
      sha256: e137b12924bbb4fbb83f45c8ccb3419ba4e5556d01d977a05a7ab4e175155c35
    sampler_input:
      rows: 83
      bytes: 7205
      sha256: ac672728d9857c417d4f51812f31b20711307f0e7ee20efacf8f38f1b3dfb42e
    sampler_manifest:
      lines: 5313
      bytes: 108942
      sha256: cf9c269a93053e64ecf9200e0ee704fb0c32d2787f721fc24f0cb711cdc33895

  universe:
    primary: primary83
    train_cells: 41
    test_cells: 42
    protocol_groups: 60
    minimum_moves: 20
    minimum_cost_split_count: 185471
    random_population_excludes_s2_reference: true
    random_population_count: 185470
    s2_reference_rank_s3_order: 169301
    derived_a_b_test_intersection: 32

  models:
    ordered: [dummy, variance, ridge, xgb]
    ranking_models: [variance, ridge, xgb]
    ranking_tie_break_order: [variance, ridge, xgb]
    exact_tie_tolerance: 0.0
    seed: 0
    stochastic_variability_estimand: false

  positive_control_a:
    models: [variance, ridge, xgb]
    governing_metric: rmse
    relative_tolerance: 0.01
    pass_comparator: less_than_or_equal
    reference_rmse:
      variance: 136.12960815429688
      ridge: 115.78919623655567
      xgb: 333.66455078125
    reference_mae:
      variance: 109.06492614746094
      ridge: 80.41317415887194
      xgb: 155.50146484375
    failure_disposition: HARD_STOP_A_POSITIVE_CONTROL_DIVERGENCE

  reference_split_control:
    gating: true
    models: [variance, ridge, xgb]
    governing_metric: rmse
    relative_tolerance: 0.01
    pass_comparator: less_than_or_equal
    reference_rmse:
      variance: 133.47593688964844
      ridge: 138.50330213051572
      xgb: 345.9460754394531
    reference_mae:
      variance: 109.73089599609375
      ridge: 83.30479497681773
      xgb: 212.07666015625
    failure_disposition: HARD_STOP_REFERENCE_SPLIT_DIVERGENCE

  sampler:
    group_key_components:
      - protocol_sha256
      - tuple_of_cell_ids_sorted_by_utf8_bytes
    group_key_serialization: protocol_sha256 + NUL + NUL_join(sorted_cell_ids)
    group_order: lexicographic_unsigned_utf8_bytes_of_serialized_group_key
    cell_order_within_group: lexicographic_unsigned_utf8_bytes
    assignment_bits:
      train: 0
      test: 1
    assignment_order: [train, test]
    continuity_with_s2_policy_readable_order: false
    seed_text: batteryml-s3-sampler|dbb142e77901cb5ee245c98af3b42e3d407c32a5|96695e534718733469ba108ee3c1372e29351710235d5b47020f6bd9ae2ce722
    seed_sha256: b9b522b9f6a194e7ab3a9eca5c3de0d583336ad773fd17beff419cfb9949c9d1
    hash_stream: SHA256(seed_bytes || uint64_be(counter))
    sampling_without_replacement: true
    modulo_bias_rejection: true
    duplicate_rank_rejection: true
    s2_reference_rank_rejection: true
    attempt_sampler_manifest_byte_identity_required: true
    attempt_sampler_manifest_mismatch_disposition: SAMPLER_REGENERATION_MISMATCH

  b2c1_axis:
    cell_id: b2c1
    protocol_group_is_singleton: true
    treatment: append_to_test_without_refit
    prediction_record_required_per_model_per_split: true
    pooled_with_primary_distribution: false
    sensitivity_minimum_space_total: 190476
    b2c1_test_split_count: 185471
    b2c1_train_split_count: 5005

  metrics:
    primary: rmse
    secondary: mae
    material_relative_change: 0.10
    no_signal_prevalence: 0.20
    material_prevalence: 0.50
    systematic_prevalence: 0.80
    dummy_composition_prevalence: 0.50
    dummy_rmse_required_comparator: greater_than_zero
    cell_concentration_top_n: 3
    protocol_concentration_top_n: 1

  ranking:
    no_material_rank_change_threshold: 0.20
    no_material_rank_change_comparator: less_than
    robust_rank_change_threshold: 0.80
    robust_rank_change_comparator: greater_than_or_equal
    robust_min_same_direction_models: 2
    model_specific_prevalent_model_count: 1

  quantiles:
    central: [0.25, 0.50, 0.75]
    tails: [0.05, 0.95]
    tail_reporting_minimum_k: 40
    definition: Hyndman_Fan_type_7

  compute:
    session_limit_source: OFFICIAL_KAGGLE_DOCUMENTATION
    session_limit_seconds: 43200
    usable_session_fraction: 0.80
    available_seconds: 34560
    measured_preprocessing_seconds: 344
    preprocessing_budget_seconds: 430
    closure_reserve_seconds: 600
    measured_max_model_run_seconds: 88
    per_model_run_budget_seconds: 110
    fixed_model_runs: 8
    fixed_overhead_seconds: 1910
    models_per_random_split: 4
    per_random_split_seconds: 440
    k_raw: 74
    k_cap: 64
    k: 64
    k_minimum_admissible: 16
    total_model_runs: 264
    projected_execution_seconds: 29470
    projected_execution_with_reserve_seconds: 30070
    projected_execution_hours: 8.35

  attempts:
    maximum_scientific_attempts: 2
    maximum_preflight_dispatches: 3
    maximum_binding_attempts: 3
    governing_attempt: first_complete_attempt
    combine_partial_attempts: false
    runner_preflight_consumes_scientific_attempt: false
    driver_start_consumes_scientific_attempt: true
    attempt_2_requires_operator_ratification: true
    attempt_2_allowed_failure_classes:
      - PLATFORM_PREEMPTION
      - PLATFORM_TIME_LIMIT
      - RESOURCE_OOM
    attempt_2_forbidden_failure_classes:
      - CODE_FAILURE
      - ASSERTION_FAILURE
      - HASH_MISMATCH
      - MEMBERSHIP_MISMATCH
      - SAMPLER_MISMATCH
      - POSITIVE_CONTROL_FAILURE
      - HARD_STOP_REFERENCE_SPLIT_DIVERGENCE
      - REFERENCE_RANK_MISMATCH
      - SAMPLER_INPUT_SCOPE_VIOLATION
      - SAMPLER_REGENERATION_MISMATCH
      - NONFINITE_SCIENTIFIC_RESULT
      - SCIENTIFIC_INCOMPLETENESS_WITHOUT_PLATFORM_EVIDENCE
    attempt_2_scope: complete_restart_of_all_runs
    two_failed_attempts_disposition: EXECUTION_BLOCKED_RESOURCE
    exhausted_preflight_dispatches_disposition: EXECUTION_BLOCKED_PREFLIGHT
    transient_binding_failure: PENDING_EXTERNAL_BINDING
    conclusive_binding_mismatch: EXECUTION_IDENTITY_UNBOUND
    binding_retry_consumes_scientific_attempt: false

  publication:
    publish_all_per_cell_predictions: true
    publish_all_b2c1_predictions: true
    publish_all_run_receipts: true
    publish_all_resolved_parameters: true
    publish_all_execution_logs: true
    publish_sampler_manifest: true
    publish_sampler_regeneration_receipt: true
    publish_checkpoints: false
    publish_checkpoint_sha256: true
    public_manifest_required: true
    projected_max_k_text_evidence_bytes: 7545671
    public_evidence_budget_bytes: 16777216
    oversize_disposition: PUBLICATION_BLOCKED_NO_EVIDENCE_OMISSION
```

---

## 3. Derived Intersection Invariant & Mathematical Proof

The A/B test-set intersection size is not a free parameter; it is an exact invariant of the minimum-cost protocol-disjoint space.

**Proof**:
1. In the `primary83` universe, $|test(A)| = 42$ and $|test(B_k)| = 42$.
2. The minimum move cost is defined as $C = 20$, which represents the total number of cells that change partition side between $A$ and $B_k$.
3. Since the partition sizes are invariant ($41$ train, $42$ test), the number of cells moving out of the test set must exactly equal the number of cells moving into the test set:
   $$\Delta_{out} = \Delta_{in} = \frac{C}{2} = \frac{20}{2} = 10$$
4. Therefore, the number of cells retained in the test set is:
   $$|test(A) \cap test(B_k)| = |test(A)| - \Delta_{out} = 42 - 10 = 32$$

Every legitimate minimum-cost protocol-disjoint split $B_k$ must have an intersection with $test(A)$ of **exactly 32 cells**. The verifier checks this invariant for every split; any deviation yields `INTERSECTION_INVARIANT_FAILURE`.

---

## 4. Execution Matrix & Two Positive Controls

The execution matrix consists of $4 \times (K + 2) = 264$ model fits:

| Partition Class | Fits | Evaluations per Fit | Role in Study |
| :--- | :---: | :--- | :--- |
| **BatteryML Split A** | 4 | Primary test (42); primary test + `b2c1` (43) | Fixed positive control baseline |
| **S2.1 Reference B** | 4 | Primary test (42); primary test + `b2c1` (43) | Reference marker & positive control |
| **Sampled Splits $B_k$ ($k=0\dots 63$)** | $4 \times 64 = 256$ | Primary test (42); primary test + `b2c1` (43) | Uniform sampled robustness distribution |

### Execution Ordering:
1. Preflight environment admission and hash verification.
2. Dataset preprocessing (isolated namespace).
3. **Four BatteryML Split A fits** (`dummy`, `variance`, `ridge`, `xgb`).
4. **Positive Control Gate 1 (Split A)**:
   $$PC_m = \frac{|RMSE_{S3,A,m} - RMSE_{S2.1,A,m}|}{RMSE_{S2.1,A,m}} \le 0.01$$
   Failure to match within $1.0\%$ aborts execution closed (`HARD_STOP_A_POSITIVE_CONTROL_DIVERGENCE`).
5. **Four S2.1 Reference Split B fits** (`dummy`, `variance`, `ridge`, `xgb`).
6. **Positive Control Gate 2 (S2.1 Reference B)**:
   $$RC_m = \frac{|RMSE_{S3,ref,m} - RMSE_{S2.1,B,m}|}{RMSE_{S2.1,B,m}} \le 0.01$$
   Failure to match within $1.0\%$ aborts execution closed (`HARD_STOP_REFERENCE_SPLIT_DIVERGENCE`).
7. **256 Sampled Model Fits** in ascending split rank order.
8. Execution closure, post-run identity binding, and adjudication.

---

## 5. Estimands & Diagnostic Metrics

### 1. Primary Operational Estimand ($D^{RMSE}_{m,k}$)
For model $m$ and split $k$:
$$D^{RMSE}_{m,k} = \frac{RMSE(B_k, m) - RMSE(A, m)}{RMSE(A, m)}$$
This explicitly measures the combined effect of:
- Held-out protocol evaluation regime;
- Natural cell-composition variation under protocol partitioning.
It is **not** characterized as an isolated causal protocol effect.

### 2. Secondary Operational Estimand ($D^{MAE}_{m,k}$)
$$D^{MAE}_{m,k} = \frac{MAE(B_k, m) - MAE(A, m)}{MAE(A, m)}$$
Reported across all splits and quantiles; provides descriptive support without adjudication weight.

### 3. Paired Diagnostic ($P_{m,k}$)
Evaluated strictly on the 32-cell intersection $I_k = test(A) \cap test(B_k)$:
$$P^{RMSE}_{m,k} = \frac{RMSE_{I_k}(B_k, m) - RMSE_{I_k}(A, m)}{RMSE_{I_k}(A, m)}$$
Holds evaluation cells constant while training sets vary.

### 4. Dummy Composition Control & Relative Skill
The dummy baseline predicts the mean training cycle life. For predictive models:
$$Skill_{m,k} = 1 - \frac{RMSE(m, k)}{RMSE(dummy, k)}$$
Precondition: $RMSE(dummy, k) > 0$ and finite; otherwise `UNDEFINED_DUMMY_SKILL_DENOMINATOR`.
If dummy $|D^{RMSE}_{dummy,k}| \ge 0.10$ across $\ge 50\%$ of splits, the `dummy_composition_sensitive` flag is active.

### 5. `b2c1` Outlier Influence ($J_{m,k}$)
Evaluated on the exact same model checkpoint without refitting:
$$J^{RMSE}_{m,k} = \frac{RMSE(test(B_k) \cup \{b2c1\}, m) - RMSE(test(B_k), m)}{RMSE(test(B_k), m)}$$
Measures the vulnerability of aggregate metrics to single extreme outlier addition.

### 6. Residual Concentrations
- **Cell-Level Concentration** (Top 3 cells):
  $$C^{cell}_{m,k} = \frac{\sum_{i \in \text{Top3}} e_i^2}{\sum_i e_i^2}$$
- **Protocol-Level Concentration** (Top 1 protocol):
  $$C^{protocol}_{m,k} = \frac{\max_g \sum_{i: protocol(i)=g} e_i^2}{\sum_i e_i^2}$$

---

## 6. Adjudication Logic & Priority Cascade

For each ranking model $m \in \{\text{variance}, \text{ridge}, \text{xgb}\}$ across $K$ splits:
- $p^{abs}_m = \frac{1}{K} \sum_k \mathbf{1}(|D^{RMSE}_{m,k}| \ge 0.10)$
- $p^{pos}_m = \frac{1}{K} \sum_k \mathbf{1}(D^{RMSE}_{m,k} \ge 0.10)$
- $p^{neg}_m = \frac{1}{K} \sum_k \mathbf{1}(D^{RMSE}_{m,k} \le -0.10)$
- $\text{material\_prevalent}_m := p^{abs}_m \ge 0.50$
- $\text{positive\_systematic}_m := p^{pos}_m \ge 0.80$
- $\text{negative\_systematic}_m := p^{neg}_m \ge 0.80$
- $\text{rank\_change\_rate} := \frac{\text{changed\_ranks\_count}}{K}$

### Global Predicates:
- $\text{NO\_SIGNAL} := (\forall m: p^{abs}_m < 0.20) \land (\text{rank\_change\_rate} < 0.20)$
- $\text{SAME\_DIRECTION\_SYSTEMATIC} := (\sum_m \text{pos\_sys}_m \ge 2) \lor (\sum_m \text{neg\_sys}_m \ge 2)$
- $\text{SYSTEMATIC\_RANK} := (\text{rank\_change\_rate} \ge 0.80) \land (\sum_m \text{mat\_prev}_m \ge 1)$
- $\text{ROBUST} := \text{SAME\_DIRECTION\_SYSTEMATIC} \lor \text{SYSTEMATIC\_RANK}$
- $\text{ONE\_MODEL} := \sum_m \text{mat\_prev}_m == 1$

### Priority Cascade (First satisfied rule governs):

| Priority | Condition | Adjudication Category |
| :---: | :--- | :--- |
| **1** | $\text{NO\_SIGNAL}$ | **`NO_MATERIAL_SIGNAL`** |
| **2** | $\text{ROBUST}$ | **`ROBUST_SYSTEMATIC_EFFECT`** |
| **3** | $\text{ONE\_MODEL}$ | **`MODEL_SPECIFIC`** |
| **4** | None of the above | **`HETEROGENEOUS_SPLIT_DEPENDENT`** |

---

## 7. Compute Budget & Mechanical $K=64$ Derivation

The compute budget formula derives $K$ strictly from the platform session limit:
- Official Kaggle Notebook session limit: $43,200\text{ s}$ ($12\text{ hours}$).
- Usable session fraction: $0.80 \implies \text{Available} = 34,560\text{ s}$.
- Fixed overhead: $430\text{ s (preprocess)} + 600\text{ s (reserve)} + 8 \times 110\text{ s (fixed runs)} = 1,910\text{ s}$.
- Per-split cost: $4\text{ models} \times 110\text{ s} = 440\text{ s}$.
- Raw capacity: $K_{raw} = \lfloor \frac{34560 - 1910}{440} \rfloor = 74$.
- Preregistered cap: $K = \min(64, 74) = \mathbf{64}$.
- Projected runtime: $29,470\text{ s}$ ($\approx 8.19\text{ h}$); with reserve: $30,070\text{ s}$ ($\approx 8.35\text{ h}$, providing $3.65\text{ h}$ margin).

---

## 8. Hard Stop Rules

| Phase | Trigger / Condition | Terminal Disposition |
| :--- | :--- | :--- |
| **Pre-run** | Governing hash mismatch | `HASH_MISMATCH` |
| **Pre-run** | DP count $C(0, 42, 20) \ne 185471$ | `SAMPLER_COUNT_MISMATCH` |
| **Pre-run** | S2.1 reference rank $\ne 169301$ | `REFERENCE_RANK_MISMATCH` |
| **Pre-run** | Sampler input scope violation | `SAMPLER_INPUT_SCOPE_VIOLATION` |
| **Pre-run** | Attempt sampler manifest mismatch | `SAMPLER_REGENERATION_MISMATCH` |
| **Control 1**| Split A divergence $> 1.0\%$ | `HARD_STOP_A_POSITIVE_CONTROL_DIVERGENCE` |
| **Control 2**| S2.1 Reference divergence $> 1.0\%$ | `HARD_STOP_REFERENCE_SPLIT_DIVERGENCE` |
| **Invariant**| Split cost $\ne 20$ or protocol overlap $> 0$ | `SPLIT_INVALID` |
| **Invariant**| A/B test intersection $\ne 32$ | `INTERSECTION_INVARIANT_FAILURE` |
| **Metric**   | Nonfinite metric or missing prediction | `NONFINITE_OR_MISSING_RESULT` |
| **Skill**    | Dummy RMSE $\le 0$ or nonfinite | `UNDEFINED_DUMMY_SKILL_DENOMINATOR` |
| **b2c1**     | Outlier evaluation alters primary checkpoint | `B2C1_LIFT_INVALID` |
| **Execution**| Missing fit out of 264 | `EXECUTION_INCOMPLETE` |
| **Binding**  | Transient external API failure | `PENDING_EXTERNAL_BINDING` |
| **Binding**  | Conclusive listing mismatch | `EXECUTION_IDENTITY_UNBOUND` |
| **Publish**  | Evidence exceeds $16\text{ MB}$ budget | `PUBLICATION_BLOCKED_NO_EVIDENCE_OMISSION` |

---

## 9. Strict Interpretation Boundary

1. **Split quantiles describe empirical partition sensitivity, not inferential confidence intervals.**
2. **Splits share a substantial fraction of cells and are not independent draws.**
3. **The primary operational estimand combines protocol holdout and composition shift.**
4. **The paired diagnostic does not isolate a pure causal protocol effect because training sets differ.**
5. **The `b2c1` lift measures sensitivity to adding an outlier cell to the test set, not training set inclusion.**
6. **No Battery Passport, commercial performance, or real-world battery degradation failure claims may be derived from this benchmark study without field validation.**
