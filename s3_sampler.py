#!/usr/bin/env python3
"""Deterministic DP Sampler and Verifier for BatteryML Protocol Robustness S3.

Preregistered constants:
- Universe: primary83 (83 cells, excluding b2c1)
- Train cells: 41, Test cells: 42
- Protocol groups: 60
- Minimum moves: 20
- Total minimum-cost splits: 185,471
- S2.1 reference rank in S3 order: 169,301
- Random population count: 185,470 (excludes reference rank)
- Derived A/B test intersection: 32 (invariant: 42 - 20/2 = 32)
- K: 64
- Seed text: batteryml-s3-sampler|dbb142e77901cb5ee245c98af3b42e3d407c32a5|96695e534718733469ba108ee3c1372e29351710235d5b47020f6bd9ae2ce722
- Seed SHA-256: b9b522b9f6a194e7ab3a9eca5c3de0d583336ad773fd17beff419cfb9949c9d1
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import struct
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

EXPECTED_SAMPLER_INPUT_SHA256 = "ac672728d9857c417d4f51812f31b20711307f0e7ee20efacf8f38f1b3dfb42e"
EXPECTED_SEED_SHA256 = "b9b522b9f6a194e7ab3a9eca5c3de0d583336ad773fd17beff419cfb9949c9d1"
SEED_TEXT = "batteryml-s3-sampler|dbb142e77901cb5ee245c98af3b42e3d407c32a5|96695e534718733469ba108ee3c1372e29351710235d5b47020f6bd9ae2ce722"

TOTAL_CELLS = 83
TRAIN_CELLS = 41
TEST_CELLS = 42
TOTAL_GROUPS = 60
MINIMUM_MOVES = 20
MINIMUM_COST_SPLIT_COUNT = 185471
S2_REFERENCE_RANK = 169301
RANDOM_POPULATION_COUNT = 185470
DERIVED_INTERSECTION = 32
K = 64


class S3Sampler:
    def __init__(self, sampler_input_path: Path) -> None:
        self.sampler_input_path = sampler_input_path
        self._load_and_validate_input()
        self._build_dp_table()

    def _load_and_validate_input(self) -> None:
        raw_bytes = self.sampler_input_path.read_bytes()
        digest = hashlib.sha256(raw_bytes).hexdigest()
        if digest != EXPECTED_SAMPLER_INPUT_SHA256:
            raise ValueError(
                f"SAMPLER_INPUT_SCOPE_VIOLATION: sha256 mismatch {digest} != {EXPECTED_SAMPLER_INPUT_SHA256}"
            )

        self.rows: list[dict[str, str]] = []
        text = raw_bytes.decode("utf-8")
        reader = csv.DictReader(text.splitlines())
        for r in reader:
            self.rows.append(r)

        if len(self.rows) != TOTAL_CELLS:
            raise ValueError(f"Expected {TOTAL_CELLS} rows, got {len(self.rows)}")

        # Group by protocol_sha256
        proto_groups: dict[str, list[dict[str, str]]] = defaultdict(list)
        for r in self.rows:
            proto_groups[r["protocol_sha256"]].append(r)

        if len(proto_groups) != TOTAL_GROUPS:
            raise ValueError(f"Expected {TOTAL_GROUPS} protocol groups, got {len(proto_groups)}")

        # Build canonically ordered group list
        # group_key: protocol_sha256 + NUL + NUL_join(sorted_cell_ids)
        # ordered by lexicographic unsigned utf-8 bytes
        self.groups: list[dict[str, Any]] = []
        for p_sha, c_list in proto_groups.items():
            sorted_cids = sorted([c["cell_id"] for c in c_list], key=lambda x: x.encode("utf-8"))
            serialized_key = p_sha.encode("utf-8") + b"\x00" + b"\x00".join([c.encode("utf-8") for c in sorted_cids])
            a_train_count = sum(1 for c in c_list if c["a_split"] == "train")
            a_test_count = sum(1 for c in c_list if c["a_split"] == "test")
            self.groups.append({
                "serialized_key": serialized_key,
                "protocol_sha": p_sha,
                "cells": sorted_cids,
                "size": len(c_list),
                "a_train": a_train_count,
                "a_test": a_test_count,
            })

        self.groups = sorted(self.groups, key=lambda g: g["serialized_key"])
        self.a_test_cells = set(r["cell_id"] for r in self.rows if r["a_split"] == "test")
        if len(self.a_test_cells) != TEST_CELLS:
            raise ValueError(f"A test set count mismatch: {len(self.a_test_cells)} != {TEST_CELLS}")

    def _build_dp_table(self) -> None:
        self.memo: dict[tuple[int, int, int], int] = {}

    def C(self, i: int, t: int, c: int) -> int:
        if t < 0 or c < 0:
            return 0
        if i == len(self.groups):
            return 1 if t == 0 and c == 0 else 0
        key = (i, t, c)
        if key in self.memo:
            return self.memo[key]
        g = self.groups[i]
        # Option 0 (train): test_added = 0, move_cost = a_test
        ans = self.C(i + 1, t, c - g["a_test"])
        # Option 1 (test): test_added = size, move_cost = a_train
        ans += self.C(i + 1, t - g["size"], c - g["a_train"])
        self.memo[key] = ans
        return ans

    def total_minimum_cost_splits(self) -> int:
        return self.C(0, TEST_CELLS, MINIMUM_MOVES)

    def compute_split_rank(self, cell_to_side: dict[str, str]) -> int:
        """Compute the rank of a split given cell assignments in S3 canonical group order."""
        rank = 0
        cur_t = TEST_CELLS
        cur_c = MINIMUM_MOVES
        for i, g in enumerate(self.groups):
            train_count = self.C(i + 1, cur_t, cur_c - g["a_test"])
            # All cells in group must have identical side
            sides = set(cell_to_side[cid] for cid in g["cells"])
            if len(sides) != 1:
                raise ValueError(f"Group {g['protocol_sha']} split across train and test")
            side = list(sides)[0]
            if side == "train":
                cur_c -= g["a_test"]
            elif side == "test":
                rank += train_count
                cur_t -= g["size"]
                cur_c -= g["a_train"]
            else:
                raise ValueError(f"Invalid side {side}")
        if cur_t != 0 or cur_c != 0:
            raise ValueError(f"Split is not exact-size minimum-cost: rem_t={cur_t}, rem_c={cur_c}")
        return rank

    def generate_ranks(self, seed_text: str = SEED_TEXT, k_count: int = K) -> list[tuple[int, int, int]]:
        """Generate k unique ranks without replacement mapped around S2 reference rank."""
        seed_bytes = hashlib.sha256(seed_text.encode("utf-8")).digest()
        seed_sha = seed_bytes.hex()
        if seed_sha != EXPECTED_SEED_SHA256:
            raise ValueError(f"Seed SHA-256 mismatch: {seed_sha} != {EXPECTED_SEED_SHA256}")

        limit = (1 << 256) - ((1 << 256) % RANDOM_POPULATION_COUNT)
        ranks: list[tuple[int, int, int]] = []
        seen: set[int] = set()
        counter = 0

        while len(ranks) < k_count:
            ctr_bytes = struct.pack(">Q", counter)
            digest = hashlib.sha256(seed_bytes + ctr_bytes).digest()
            x = int.from_bytes(digest, "big")
            counter += 1
            if x >= limit:
                continue
            u = x % RANDOM_POPULATION_COUNT
            r = u if u < S2_REFERENCE_RANK else u + 1
            if r in seen:
                continue
            seen.add(r)
            ranks.append((len(ranks), counter - 1, r))

        return ranks

    def unrank(self, target_rank: int) -> dict[str, str]:
        """Unrank a target rank to a dict of cell_id -> 'train' | 'test'."""
        if not (0 <= target_rank < MINIMUM_COST_SPLIT_COUNT):
            raise ValueError(f"Rank out of bounds: {target_rank}")
        cur_t = TEST_CELLS
        cur_c = MINIMUM_MOVES
        rem_rank = target_rank
        assignments: dict[str, str] = {}
        for i, g in enumerate(self.groups):
            train_count = self.C(i + 1, cur_t, cur_c - g["a_test"])
            if rem_rank < train_count:
                for cid in g["cells"]:
                    assignments[cid] = "train"
                cur_c -= g["a_test"]
            else:
                for cid in g["cells"]:
                    assignments[cid] = "test"
                rem_rank -= train_count
                cur_t -= g["size"]
                cur_c -= g["a_train"]
        if cur_t != 0 or cur_c != 0 or rem_rank != 0:
            raise RuntimeError(f"Unranking failure for rank {target_rank}: t={cur_t}, c={cur_c}, rem={rem_rank}")
        return assignments

    def verify_split_invariants(self, assignments: dict[str, str]) -> dict[str, Any]:
        """Verify all invariants for a generated split."""
        train_cells = [cid for cid, side in assignments.items() if side == "train"]
        test_cells = [cid for cid, side in assignments.items() if side == "test"]

        if len(train_cells) != TRAIN_CELLS:
            raise ValueError(f"Train cells mismatch: {len(train_cells)} != {TRAIN_CELLS}")
        if len(test_cells) != TEST_CELLS:
            raise ValueError(f"Test cells mismatch: {len(test_cells)} != {TEST_CELLS}")

        # Check protocol disjointness
        cell_to_proto = {r["cell_id"]: r["protocol_sha256"] for r in self.rows}
        train_protos = set(cell_to_proto[c] for c in train_cells)
        test_protos = set(cell_to_proto[c] for c in test_cells)
        overlap = train_protos.intersection(test_protos)
        if len(overlap) > 0:
            raise ValueError(f"Protocol overlap detected: {len(overlap)} overlapping protocols")

        # Check cost
        cost = sum(1 for cid in train_cells if cid in self.a_test_cells) + sum(
            1 for cid in test_cells if cid not in self.a_test_cells
        )
        if cost != MINIMUM_MOVES:
            raise ValueError(f"Move cost mismatch: {cost} != {MINIMUM_MOVES}")

        # Check intersection with A test
        intersection_count = len(set(test_cells).intersection(self.a_test_cells))
        if intersection_count != DERIVED_INTERSECTION:
            raise ValueError(
                f"INTERSECTION_INVARIANT_FAILURE: {intersection_count} != {DERIVED_INTERSECTION}"
            )

        return {
            "train_cells": len(train_cells),
            "test_cells": len(test_cells),
            "protocol_overlap": 0,
            "move_cost": cost,
            "intersection_with_a_test": intersection_count,
        }

    def generate_manifest_rows(
        self, ranks: list[tuple[int, int, int]]
    ) -> list[str]:
        lines = ["split_index,split_rank,cell_id,assignment\n"]
        for s_idx, _, r in ranks:
            asgn = self.unrank(r)
            self.verify_split_invariants(asgn)
            for cid in sorted(asgn.keys(), key=lambda x: x.encode("utf-8")):
                lines.append(f"{s_idx},{r},{cid},{asgn[cid]}\n")
        return lines


def verify_full_s2_manifest_reference_rank(s2_manifest_path: Path) -> int:
    """Read full S2 manifest and derive S2.1 B rank in S3 canonical group order."""
    cells = []
    with open(s2_manifest_path, "r", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            if r["universe"] == "primary83":
                cells.append(r)

    cell_to_b = {r["cell_id"]: r["b_split"] for r in cells}
    # Create temporary sampler input to instantiate S3Sampler
    primary_sorted = sorted(cells, key=lambda x: (x["universe"].encode("utf-8"), x["cell_id"].encode("utf-8")))
    out_lines = ["universe,cell_id,a_split,protocol_sha256\n"]
    for r in primary_sorted:
        out_lines.append(f"{r['universe']},{r['cell_id']},{r['a_split']},{r['protocol_sha256']}\n")
    
    import tempfile
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False) as tf:
        tf.write("".join(out_lines))
        tf_path = Path(tf.name)

    try:
        sampler = S3Sampler(tf_path)
        rank = sampler.compute_split_rank(cell_to_b)
        return rank
    finally:
        tf_path.unlink(missing_ok=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="BatteryML S3 Sampler & Verifier")
    parser.add_argument(
        "--sampler-input",
        type=Path,
        default=Path("sampler_input.csv"),
        help="Path to canonical 4-column sampler input CSV",
    )
    parser.add_argument(
        "--export-manifest",
        type=Path,
        default=None,
        help="Path to write s3-split-manifest.csv",
    )
    parser.add_argument(
        "--export-ranks",
        type=Path,
        default=None,
        help="Path to write s3-sampler-ranks.json",
    )
    parser.add_argument(
        "--verify-ref-manifest",
        type=Path,
        default=None,
        help="Path to S2.1 full manifest to verify S2.1 B reference rank == 169301",
    )
    args = parser.parse_args()

    print(f"Loading sampler input from {args.sampler_input}...")
    sampler = S3Sampler(args.sampler_input)

    dp_count = sampler.total_minimum_cost_splits()
    print(f"DP count C(0, 42, 20): {dp_count}")
    if dp_count != MINIMUM_COST_SPLIT_COUNT:
        print(f"ERROR: DP count mismatch {dp_count} != {MINIMUM_COST_SPLIT_COUNT}", file=sys.stderr)
        sys.exit(1)

    if args.verify_ref_manifest:
        derived_ref_rank = verify_full_s2_manifest_reference_rank(args.verify_ref_manifest)
        print(f"Derived S2.1 B reference rank: {derived_ref_rank}")
        if derived_ref_rank != S2_REFERENCE_RANK:
            print(
                f"ERROR: REFERENCE_RANK_MISMATCH {derived_ref_rank} != {S2_REFERENCE_RANK}",
                file=sys.stderr,
            )
            sys.exit(1)

    print(f"Generating {K} ranks from seed text...")
    ranks = sampler.generate_ranks()
    print(f"Generated {len(ranks)} unique ranks.")

    manifest_lines = sampler.generate_manifest_rows(ranks)
    manifest_text = "".join(manifest_lines)
    manifest_sha = hashlib.sha256(manifest_text.encode("utf-8")).hexdigest()
    print(f"Split manifest lines: {len(manifest_lines)}")
    print(f"Split manifest bytes: {len(manifest_text.encode('utf-8'))}")
    print(f"Split manifest SHA-256: {manifest_sha}")

    if args.export_manifest:
        args.export_manifest.write_text(manifest_text, encoding="utf-8")
        print(f"Exported manifest to {args.export_manifest}")

    if args.export_ranks:
        ranks_payload = [
            {"split_index": s_idx, "counter": ctr, "rank": r}
            for s_idx, ctr, r in ranks
        ]
        args.export_ranks.write_text(json.dumps(ranks_payload, indent=2) + "\n", encoding="utf-8")
        print(f"Exported ranks to {args.export_ranks}")

    print("ALL VERIFICATIONS PASSED.")


if __name__ == "__main__":
    main()
