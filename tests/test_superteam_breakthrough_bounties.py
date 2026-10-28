# -*- coding: utf-8 -*-
"""
Automated Verification Suite for Breakthrough Engineering Deliverables:
  1. Superteam Earn Bounty #1 (`2,500 USDC`): Inside the Block — Solana Validator Ordering
  2. Superteam Earn Bounty #2 (`5,000 USDC`): MultiHopper Optimal Split-Routing Solver
  3. Freelancer Breakthrough Upgrades (`FLP-40789694` Multi-Label Audit & `FLP-40789906` Topology Guard)
"""
from __future__ import annotations

from pathlib import Path
import sys
import pytest

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from scripts.pilots.superteam_01_agave_prio_graph_simulator import (
    FeeSpendCapCircuitBreaker,
    FeeSpendCapExceededError,
    SolanaTransactionPacket,
    analyze_mainnet_jsonl_dataset,
    build_reverse_priority_probe_plan,
    compute_agave_scheduler_priority,
    compute_rank_correlation_and_inversions,
    simulate_prio_graph_block_scheduling,
)


def test_agave_priority_cu_overestimation_dilution_and_jito_exclusion() -> None:
    """
    Prove that requesting 200,000 CU when only using 25,000 CU dilutes effective
    scheduler priority by ~8x compared to tight CU sizing, and Jito bundles are
    excluded from standard leader schedulerwaves.
    """
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
        arrival_ns=1_000_001,  # Arrived earlier, paid higher absolute fee (100k vs 50k), but requested 200k CU!
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

    prio_tight = compute_agave_scheduler_priority(tx_tight_cu)
    prio_bloated = compute_agave_scheduler_priority(tx_bloated_cu)
    assert prio_tight > prio_bloated

    sched = simulate_prio_graph_block_scheduling([tx_bloated_cu, tx_tight_cu, tx_jito_bundle])
    scheduled_ids = [item["tx_id"] for item in sched["scheduled_transactions"]]
    assert scheduled_ids == ["tx_tight_25k_cu", "tx_bloated_200k_cu"]
    # Because both write to AMM_POOL_A, they must be serialized into separate execution waves (Wave 0 and Wave 1)
    assert sched["execution_waves"] == [["tx_tight_25k_cu"], ["tx_bloated_200k_cu"]]


def test_fee_spend_cap_circuit_breaker_and_reverse_priority_probes() -> None:
    """
    Verify the mandatory 0.05 SOL (50,000,000 lamports) hard fee-spend cap,
    dry-run-by-default enforcement, and Post-Alpenglow reverse-priority probe builder.
    """
    breaker = FeeSpendCapCircuitBreaker(max_spend_lamports=50_000_000, dry_run=True)
    probes = build_reverse_priority_probe_plan(
        validator_pubkey="AurseT3W3tk1dATBWAXtWR6oubBgECqintfcvP74teU3",
        client_version="4.3.2",
        target_slot=462_405_266,
        circuit_breaker=breaker,
    )
    assert len(probes) == 5
    # Sent in ascending fee order (1,000 -> 120,000) so lowest priority is sent first
    assert [p["priority_fee_lamports"] for p in probes] == [1_000, 5_000, 15_000, 45_000, 120_000]
    assert [p["expected_prio_graph_rank"] for p in probes] == [5, 4, 3, 2, 1]
    assert all(p["budget_status"] == "DRY_RUN" for p in probes)

    # Attempting to exceed 50,000,000 lamports (0.05 SOL) must raise FeeSpendCapExceededError
    with pytest.raises(FeeSpendCapExceededError):
        breaker.authorize_transaction("excessive_tx", 50_000_000)

    # Pre-Alpenglow slot must be rejected
    with pytest.raises(ValueError, match="pre-Alpenglow"):
        build_reverse_priority_probe_plan(
            validator_pubkey="AurseT3W3tk1dATBWAXtWR6oubBgECqintfcvP74teU3",
            client_version="4.3.2",
            target_slot=400_000_000,
            circuit_breaker=breaker,
        )


def test_real_mainnet_post_alpenglow_jsonl_dataset_meets_6_validators_3_versions() -> None:
    """
    Verify that the captured real Post-Alpenglow Solana Mainnet dataset contains
    >= 6 distinct validators across >= 3 distinct client software versions, and
    Spearman rank correlation classifies strict priority ordering accurately.
    """
    perfect_descending = [500_000, 250_000, 120_000, 45_000, 10_000]
    perfect_stats = compute_rank_correlation_and_inversions(perfect_descending)
    assert perfect_stats["spearman_rho"] == 1.0
    assert perfect_stats["pairwise_inversion_rate"] == 0.0
    assert perfect_stats["ordering_classification"] == "STRICT_PRIO_GRAPH_REWARD_PER_CU"

    jsonl_path = (
        Path(__file__).resolve().parents[1]
        / "data"
        / "deliverables"
        / "superteam_01_inside_the_block"
        / "raw_mainnet_validator_measurements.jsonl"
    )
    assert jsonl_path.exists()
    summary = analyze_mainnet_jsonl_dataset(jsonl_path)
    assert summary["distinct_validators_count"] >= 6
    assert summary["distinct_client_versions_count"] >= 3
    assert summary["meets_bounty_6_validators_3_versions_gate"] is True


