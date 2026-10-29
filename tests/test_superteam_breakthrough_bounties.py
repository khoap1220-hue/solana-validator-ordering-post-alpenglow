# -*- coding: utf-8 -*-
"""
Zero-Dependency `unittest` + `pytest` Verification Suite for:
Inside the Block: How Solana Validators Order Transactions (Post-Alpenglow Mainnet Study)
"""
from __future__ import annotations

from pathlib import Path
import sys
import unittest

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from scripts.pilots.superteam_01_agave_prio_graph_simulator import (
    FeeSpendCapCircuitBreaker,
    FeeSpendCapExceededError,
    SolanaTransactionPacket,
    analyze_fee_payer_write_lock_serialization,
    analyze_mainnet_jsonl_dataset,
    build_latin_square_probe_matrix,
    build_reverse_priority_probe_plan,
    compute_agave_scheduler_priority,
    compute_rank_correlation_and_inversions,
    simulate_prio_graph_block_scheduling,
)


class TestSolanaValidatorOrderingPostAlpenglow(unittest.TestCase):
    """
    Runs under both `python -m unittest discover -s tests -v` (inside `python:3.11-slim` Docker
    with zero pip dependencies) and `pytest`.
    """

    def test_01_agave_priority_cu_overestimation_dilution_and_jito_exclusion(self) -> None:
        tx_tight_cu = SolanaTransactionPacket(
            tx_id="tx_tight_25k_cu",
            arrival_ns=1_000_005,
            requested_cu=25_000,
            actual_cu_used=24_500,
            total_priority_fee_lamports=50_000,
            writable_accounts=("AMM_POOL_A",),
            readonly_accounts=("TOKEN_PROGRAM",),
        )
        tx_bloated_cu = SolanaTransactionPacket(
            tx_id="tx_bloated_200k_cu",
            arrival_ns=1_000_001,
            requested_cu=200_000,
            actual_cu_used=24_500,
            total_priority_fee_lamports=100_000,
            writable_accounts=("AMM_POOL_A",),
            readonly_accounts=("TOKEN_PROGRAM",),
        )
        tx_jito_bundle = SolanaTransactionPacket(
            tx_id="tx_jito_out_of_scope",
            arrival_ns=999_999,
            requested_cu=25_000,
            actual_cu_used=20_000,
            total_priority_fee_lamports=500_000,
            writable_accounts=("AMM_POOL_A",),
            readonly_accounts=("TOKEN_PROGRAM",),
            is_jito_bundle=True,
        )

        self.assertGreater(
            compute_agave_scheduler_priority(tx_tight_cu),
            compute_agave_scheduler_priority(tx_bloated_cu),
        )
        sched = simulate_prio_graph_block_scheduling([tx_bloated_cu, tx_tight_cu, tx_jito_bundle])
        scheduled_ids = [item["tx_id"] for item in sched["scheduled_transactions"]]
        self.assertEqual(scheduled_ids, ["tx_tight_25k_cu", "tx_bloated_200k_cu"])
        self.assertEqual(sched["execution_waves"], [["tx_tight_25k_cu"], ["tx_bloated_200k_cu"]])

    def test_02_fee_spend_cap_circuit_breaker_and_reverse_priority_probes(self) -> None:
        breaker = FeeSpendCapCircuitBreaker(max_spend_lamports=50_000_000, dry_run=True)
        probes = build_reverse_priority_probe_plan(
            validator_pubkey="AurseT3W3tk1dATBWAXtWR6oubBgECqintfcvP74teU3",
            client_version="4.3.2",
            target_slot=462_405_266,
            circuit_breaker=breaker,
        )
        self.assertEqual(len(probes), 5)
        self.assertEqual(
            [p["priority_fee_lamports"] for p in probes],
            [1_000, 5_000, 15_000, 45_000, 120_000],
        )
        self.assertEqual([p["expected_prio_graph_rank"] for p in probes], [5, 4, 3, 2, 1])
        self.assertTrue(all(p["budget_status"] == "DRY_RUN" for p in probes))

        with self.assertRaises(FeeSpendCapExceededError):
            breaker.authorize_transaction("excessive_tx", 50_000_000)

        with self.assertRaises(ValueError):
            build_reverse_priority_probe_plan(
                validator_pubkey="AurseT3W3tk1dATBWAXtWR6oubBgECqintfcvP74teU3",
                client_version="4.3.2",
                target_slot=400_000_000,
                circuit_breaker=breaker,
            )

    def test_03_latin_square_probe_matrix_decorrelates_send_order_from_fee(self) -> None:
        breaker = FeeSpendCapCircuitBreaker(max_spend_lamports=50_000_000, dry_run=True)
        latin = build_latin_square_probe_matrix(target_slot=462_405_266, circuit_breaker=breaker)
        self.assertEqual(latin["burst_count"], 4)
        self.assertEqual(latin["txs_per_burst"], 4)
        self.assertTrue(latin["position_fee_sums_equal"])
        self.assertEqual(latin["position_fee_sums"], [66_000, 66_000, 66_000, 66_000])

    def test_04_fee_payer_write_lock_serialization_vs_disjoint_payer_parallelism(self) -> None:
        res = analyze_fee_payer_write_lock_serialization()
        self.assertEqual(res["shared_payer_wave_count"], 4)
        self.assertEqual(res["disjoint_payer_wave_count"], 1)
        self.assertTrue(res["single_payer_serializes_waves"])
        self.assertEqual(
            res["shared_payer_ordered_ids"],
            ["shared_payer_tx_3", "shared_payer_tx_2", "shared_payer_tx_1", "shared_payer_tx_0"],
        )

    def test_05_real_mainnet_post_alpenglow_jsonl_dataset_meets_6_validators_3_versions(self) -> None:
        perfect_descending = [500_000, 250_000, 120_000, 45_000, 10_000]
        perfect_stats = compute_rank_correlation_and_inversions(perfect_descending)
        self.assertEqual(perfect_stats["spearman_rho"], 1.0)
        self.assertEqual(perfect_stats["pairwise_inversion_rate"], 0.0)
        self.assertEqual(
            perfect_stats["ordering_classification"], "STRICT_PRIO_GRAPH_REWARD_PER_CU"
        )

        jsonl_path = (
            ROOT_DIR
            / "data"
            / "deliverables"
            / "superteam_01_inside_the_block"
            / "raw_mainnet_validator_measurements.jsonl"
        )
        self.assertTrue(jsonl_path.exists())
        summary = analyze_mainnet_jsonl_dataset(jsonl_path)
        self.assertGreaterEqual(summary["distinct_validators_count"], 6)
        self.assertGreaterEqual(summary["distinct_client_versions_count"], 3)
        self.assertTrue(summary["meets_bounty_6_validators_3_versions_gate"])


if __name__ == "__main__":
    unittest.main()
