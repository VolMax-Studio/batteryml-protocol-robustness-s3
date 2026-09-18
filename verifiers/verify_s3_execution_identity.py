#!/usr/bin/env python3
"""Independent Verifier for S3 Governing Execution Identity.

Verifies:
1. All 64 split-summary.json files from the execution run.
2. Unique draw_index and split_rank (count == 64).
3. Exact min rank (1666) and max rank (184309).
4. Draw order rank hash == 1d84b7bf864945a26ec0a5d2feec754b6ed6b4bf50b9f4e5b02bc45720b0ff02
5. Ascending rank hash == 0f2de17c98e615023ef5966630fd93962382c4566c36a43b0d386bd0a8dbfc40
6. Test membership commitment hash == 53a157ecd49c0a238cd5028c6ab840431a7ecb600b067290ee51645820cb5ada
7. Byte-identical row-for-row match against s3-test-membership-commitment.csv.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

EXPECTED_DRAW_HASH = "1d84b7bf864945a26ec0a5d2feec754b6ed6b4bf50b9f4e5b02bc45720b0ff02"
EXPECTED_ASC_HASH = "0f2de17c98e615023ef5966630fd93962382c4566c36a43b0d386bd0a8dbfc40"
EXPECTED_MEMBERSHIP_HASH = "53a157ecd49c0a238cd5028c6ab840431a7ecb600b067290ee51645820cb5ada"
EXPECTED_MIN_RANK = 1666
EXPECTED_MAX_RANK = 184309
EXPECTED_COUNT = 64


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def verify_identity(output_root: Path, commitment_file: Path) -> dict[str, object]:
    sampled_dir = output_root / "s3-artifact" / "results" / "sampled"
    split_dirs = sorted([d for d in sampled_dir.iterdir() if d.is_dir()])
    if len(split_dirs) != EXPECTED_COUNT:
        raise RuntimeError(f"Expected {EXPECTED_COUNT} sampled dirs, found {len(split_dirs)}")

    summaries = []
    for d in split_dirs:
        p = d / "split-summary.json"
        if not p.is_file():
            raise RuntimeError(f"Missing split-summary.json in {d}")
        s_data = json.loads(p.read_text())

        # Load test_cell_ids from run-receipt.json and ensure all models agree
        test_cells = None
        for m in ["ridge", "variance", "xgb", "dummy"]:
            rcpt_p = d / m / "run-receipt.json"
            if not rcpt_p.is_file():
                raise RuntimeError(f"Missing {rcpt_p}")
            rcpt = json.loads(rcpt_p.read_text())
            m_cells = rcpt["test_cell_ids"]
            if test_cells is None:
                test_cells = m_cells
            elif test_cells != m_cells:
                raise RuntimeError(f"Model test_cell_ids disagreement in {d}: {m}")

        s_data["test_cell_ids"] = test_cells
        summaries.append(s_data)

    draw_indices = [s["draw_index"] for s in summaries]
    split_ranks = [s["split_rank"] for s in summaries]

    if len(draw_indices) != EXPECTED_COUNT:
        raise RuntimeError(f"Invalid count: {len(draw_indices)} != {EXPECTED_COUNT}")
    if len(set(draw_indices)) != EXPECTED_COUNT:
        raise RuntimeError(f"Duplicate draw_indices found: {len(set(draw_indices))} unique")
    if len(set(split_ranks)) != EXPECTED_COUNT:
        raise RuntimeError(f"Duplicate split_ranks found: {len(set(split_ranks))} unique")

    min_rank = min(split_ranks)
    max_rank = max(split_ranks)
    if min_rank != EXPECTED_MIN_RANK or max_rank != EXPECTED_MAX_RANK:
        raise RuntimeError(f"Rank bounds mismatch: min={min_rank} (expected {EXPECTED_MIN_RANK}), max={max_rank} (expected {EXPECTED_MAX_RANK})")

    # 1. Draw order hash
    by_draw = sorted(summaries, key=lambda s: s["draw_index"])
    draw_ranks_text = "".join(f"{s['split_rank']}\n" for s in by_draw)
    draw_hash = sha256_text(draw_ranks_text)
    if draw_hash != EXPECTED_DRAW_HASH:
        raise RuntimeError(f"Draw order hash mismatch: {draw_hash} vs {EXPECTED_DRAW_HASH}")

    # 2. Ascending rank hash
    by_rank = sorted(summaries, key=lambda s: s["split_rank"])
    asc_ranks_text = "".join(f"{s['split_rank']}\n" for s in by_rank)
    asc_hash = sha256_text(asc_ranks_text)
    if asc_hash != EXPECTED_ASC_HASH:
        raise RuntimeError(f"Ascending rank hash mismatch: {asc_hash} vs {EXPECTED_ASC_HASH}")

    # 3. Membership commitment (no header in canonical s3-test-membership-commitment.csv)
    rows = []
    for s in by_draw:
        cells = sorted(s["test_cell_ids"])
        cell_str = "|".join(cells)
        rows.append(f"{s['draw_index']},{s['split_rank']},{cell_str}\n")
    reconstructed_text = "".join(rows)
    reconstructed_hash = sha256_text(reconstructed_text)

    if reconstructed_hash != EXPECTED_MEMBERSHIP_HASH:
        raise RuntimeError(f"Membership commitment hash mismatch: {reconstructed_hash} vs {EXPECTED_MEMBERSHIP_HASH}")

    expected_commitment_text = commitment_file.read_text()
    if reconstructed_text != expected_commitment_text:
        raise RuntimeError("Reconstructed membership text differs from commitment file")

    return {
        "status": "PASS",
        "count": EXPECTED_COUNT,
        "min_rank": min_rank,
        "max_rank": max_rank,
        "draw_order_rank_hash": draw_hash,
        "ascending_rank_hash": asc_hash,
        "membership_commitment_hash": reconstructed_hash,
        "row_for_row_text_match": True,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-root", type=Path, default=Path("s3_execution_output"))
    parser.add_argument("--commitment-file", type=Path, default=Path("s3-test-membership-commitment.csv"))
    args = parser.parse_args()

    try:
        res = verify_identity(args.output_root.resolve(), args.commitment_file.resolve())
        print(json.dumps(res, indent=2))
        print("\nALL GOVERNING IDENTITY COMMITMENTS VERIFIED: PASS")
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
