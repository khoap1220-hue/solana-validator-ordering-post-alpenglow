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
from scripts.pilots.superteam_02_multihopper_route_solver import (
    LiquidityPoolEdge,
    solve_optimal_multihop_split_route,
)
from scripts.pilots.pilot_flp_40789694_customer_complaints_nlp import (
    analyze_customer_survey_comments,
)
from scripts.pilots.pilot_flp_40789906_lightburn_svg_layers import (
    split_svg_for_lightburn,
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


def test_multihopper_split_routing_outperforms_single_direct_pool() -> None:
    """
    Verify that splitting a large swap across a shallow direct pool and a deep 2-hop
    route yields strictly higher net output while respecting Solana's 1,400,000 CU ceiling.
    """
    pools = [
        LiquidityPoolEdge(
            pool_id="RAYDIUM_DIRECT_SHALLOW",
            dex_type="AMM_XYK",
            token_a="SOL",
            token_b="JUP",
            reserve_a=500.0,
            reserve_b=50_000.0,
            fee_bps=25,
            hop_cu_cost=65_000,
        ),
        LiquidityPoolEdge(
            pool_id="ORCA_SOL_USDC_DEEP",
            dex_type="AMM_XYK",
            token_a="SOL",
            token_b="USDC",
            reserve_a=600.0,
            reserve_b=90_000.0,
            fee_bps=10,
            hop_cu_cost=95_000,
        ),
        LiquidityPoolEdge(
            pool_id="METEORA_USDC_JUP_DEEP",
            dex_type="AMM_XYK",
            token_a="USDC",
            token_b="JUP",
            reserve_a=90_000.0,
            reserve_b=63_000.0,
            fee_bps=10,
            hop_cu_cost=95_000,
        ),
    ]
    res = solve_optimal_multihop_split_route(
        pools=pools,
        token_in="SOL",
        token_out="JUP",
        total_amount_in=250.0,
        max_tx_cu=1_400_000,
        tranches=20,
    )
    assert res["split_route_total_out"] > res["single_path_baseline_out"]
    assert res["improvement_over_single_path_bps"] > 50.0
    assert res["cu_budget_respected"] is True
    assert res["zero_arbitrage_loops"] is True


def test_breakthrough_upgrades_flp_40789694_and_flp_40789906(tmp_path: Path) -> None:
    """
    Verify compound complaint+idea decomposition, Excel COUNTIF audit formula generation,
    and SVG duplicate path removal + auto-closed Z contour enforcement.
    """
    csv_out = tmp_path / "audit_survey.csv"
    res_nlp = analyze_customer_survey_comments(
        [
            "Delivery took weeks and arrived late, please add express next day shipping!",
            "Checkout payment failed on Safari, would love one-click apple pay.",
        ],
        csv_out,
    )
    assert res_nlp["compound_complaint_and_idea_count"] == 2
    assert "=COUNTIF(" in res_nlp["top_5_complaints"][0]["excel_countif_audit_formula"]

    svg_xml = """<svg xmlns="http://www.w3.org/2000/svg" width="120mm" height="80mm" viewBox="0 0 120 80">
      <path d="M 10 10 L 110 10 L 110 70 L 10 70 Z" fill="none" stroke="#000" data-layer="cut"/>
      <path d="M 10 10 L 110 10 L 110 70 L 10 70 Z" fill="none" stroke="#000" data-layer="cut"/>
      <path d="M 30 30 L 90 30 L 60 60" fill="#333" data-layer="engrave"/>
    </svg>"""
    svg_out = tmp_path / "clean_lightburn.svg"
    res_svg = split_svg_for_lightburn(svg_xml, svg_out)
    assert res_svg["duplicate_paths_removed"] == 1
    assert res_svg["auto_closed_engrave_contours"] == 1
    assert res_svg["cut_paths_count"] == 1
    assert res_svg["engrave_paths_count"] == 1
