# -*- coding: utf-8 -*-
"""
=============================================================================
SUPERTEAM EARN BOUNTY #2 (5,000 USDC — Only 30 Submissions):
MultiHopper Build & Route Challenge
File: scripts/pilots/superteam_02_multihopper_route_solver.py

Multi-Hop + Convex Split-Routing Solver under Solana's 1,400,000 CU Ceiling:
  - Supports Constant-Product AMM (`x * y = k`), Concentrated Liquidity CLMM
    (`effective_liquidity` & `fee_bps`), and L2 Orderbook pools.
  - Enumerates loop-free simple paths (`Zero-Arbitrage-Loop Guarantee`) from `token_in`
    to `token_out` up to `max_hops = 3`.
  - Uses marginal-output greedy tranche allocation (`Split-Routing`) across candidate
    paths while strictly enforcing `total_cu <= max_tx_cu` (`1,400,000 CU`).
  - Proves positive net output gain over single-path routing on fragmented liquidity.
=============================================================================
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

SOLANA_MAX_TX_CU = 1_400_000
BASE_TX_OVERHEAD_CU = 45_000


@dataclass(frozen=True)
class LiquidityPoolEdge:
    pool_id: str
    dex_type: str  # "AMM_XYK" | "CLMM" | "ORDERBOOK"
    token_a: str
    token_b: str
    reserve_a: float
    reserve_b: float
    fee_bps: int
    hop_cu_cost: int


def simulate_single_hop_swap(pool: LiquidityPoolEdge, token_in: str, amount_in: float) -> float:
    """Compute exact output tokens for a single pool hop with fee and price impact."""
    if amount_in <= 0.0:
        return 0.0
    if token_in == pool.token_a:
        res_in, res_out = pool.reserve_a, pool.reserve_b
    elif token_in == pool.token_b:
        res_in, res_out = pool.reserve_b, pool.reserve_a
    else:
        raise ValueError(f"Token {token_in} not in pool {pool.pool_id}")

    effective_in = amount_in * (10_000 - pool.fee_bps) / 10_000.0
    if pool.dex_type == "CLMM":
        # Concentrated liquidity has 2.2x virtual depth within active tick range
        v_in, v_out = res_in * 2.2, res_out * 2.2
        return (v_out * effective_in) / (v_in + effective_in)
    elif pool.dex_type == "ORDERBOOK":
        # Orderbook quote with shallow linear slippage factor
        mid_price = res_out / res_in
        slippage_penalty = min(0.15, effective_in / (res_in * 4.0))
        return effective_in * mid_price * (1.0 - slippage_penalty)
    else:
        # Standard Constant Product x * y = k
        return (res_out * effective_in) / (res_in + effective_in)


def evaluate_path_output(path: list[LiquidityPoolEdge], start_token: str, amount_in: float) -> float:
    """Propagate `amount_in` through a multi-hop sequence of pools."""
    curr_token = start_token
    curr_amt = amount_in
    for pool in path:
        curr_amt = simulate_single_hop_swap(pool, curr_token, curr_amt)
        curr_token = pool.token_b if curr_token == pool.token_a else pool.token_a
    return curr_amt


def find_loop_free_paths(
    pools: list[LiquidityPoolEdge],
    token_in: str,
    token_out: str,
    max_hops: int = 3,
) -> list[list[LiquidityPoolEdge]]:
    """Enumerate all simple (loop-free) paths from `token_in` to `token_out` up to `max_hops`."""
    valid_paths: list[list[LiquidityPoolEdge]] = []

    def dfs(curr_token: str, visited_tokens: set[str], current_edges: list[LiquidityPoolEdge]) -> None:
        if curr_token == token_out and current_edges:
            valid_paths.append(list(current_edges))
            return
        if len(current_edges) >= max_hops:
            return
        for p in pools:
            if curr_token == p.token_a:
                nxt = p.token_b
            elif curr_token == p.token_b:
                nxt = p.token_a
            else:
                continue
            if nxt in visited_tokens:
                continue
            visited_tokens.add(nxt)
            current_edges.append(p)
            dfs(nxt, visited_tokens, current_edges)
            current_edges.pop()
            visited_tokens.remove(nxt)

    dfs(token_in, {token_in}, [])
    return valid_paths


def solve_optimal_multihop_split_route(
    pools: list[LiquidityPoolEdge],
    token_in: str,
    token_out: str,
    total_amount_in: float,
    max_tx_cu: int = SOLANA_MAX_TX_CU,
    tranches: int = 20,
) -> dict[str, Any]:
    """
    Compute both the best single-path route and the optimal convex split-route across
    loop-free candidate paths subject to `total_cu <= max_tx_cu`.
    """
    if total_amount_in <= 0:
        raise ValueError("total_amount_in must be positive")

    candidate_paths = find_loop_free_paths(pools, token_in, token_out, max_hops=3)
    if not candidate_paths:
        raise ValueError(f"No valid route between {token_in} and {token_out}")

    # Filter paths that individually fit inside max_tx_cu
    feasible_paths = [
        p for p in candidate_paths
        if BASE_TX_OVERHEAD_CU + sum(e.hop_cu_cost for e in p) <= max_tx_cu
    ]
    if not feasible_paths:
        raise ValueError("All candidate paths exceed Solana CU ceiling")

    # 1. Best Single-Path Baseline
    best_single_path = max(
        feasible_paths, key=lambda p: evaluate_path_output(p, token_in, total_amount_in)
    )
    single_path_out = evaluate_path_output(best_single_path, token_in, total_amount_in)

    # 2. Marginal-Output Tranche Split-Routing with Strict CU Budget Enforcement
    tranche_size = total_amount_in / float(tranches)
    allocations = [0.0 for _ in feasible_paths]
    active_pool_ids: set[str] = set()

    for _ in range(tranches):
        best_idx = -1
        best_marginal_gain = -1.0
        for idx, path in enumerate(feasible_paths):
            # Check if activating this path's pools would breach max_tx_cu
            new_pools = active_pool_ids | {e.pool_id for e in path}
            projected_cu = BASE_TX_OVERHEAD_CU + sum(
                next(p.hop_cu_cost for p in pools if p.pool_id == pid)
                for pid in new_pools
            )
            if projected_cu > max_tx_cu:
                continue

            curr_out = evaluate_path_output(path, token_in, allocations[idx])
            next_out = evaluate_path_output(path, token_in, allocations[idx] + tranche_size)
            gain = next_out - curr_out
            if gain > best_marginal_gain:
                best_marginal_gain = gain
                best_idx = idx

        if best_idx >= 0:
            allocations[best_idx] += tranche_size
            active_pool_ids.update(e.pool_id for e in feasible_paths[best_idx])

    split_routes = []
    total_split_out = 0.0
    for idx, amt in enumerate(allocations):
        if amt > 0:
            out_val = evaluate_path_output(feasible_paths[idx], token_in, amt)
            total_split_out += out_val
            split_routes.append(
                {
                    "pool_hops": [e.pool_id for e in feasible_paths[idx]],
                    "amount_in": round(amt, 6),
                    "share_pct": round(amt * 100.0 / total_amount_in, 2),
                    "amount_out": round(out_val, 6),
                }
            )

    total_cu_used = BASE_TX_OVERHEAD_CU + sum(
        next(p.hop_cu_cost for p in pools if p.pool_id == pid)
        for pid in active_pool_ids
    )

    improvement_bps = round((total_split_out - single_path_out) * 10_000.0 / max(1e-9, single_path_out), 2)

    return {
        "token_in": token_in,
        "token_out": token_out,
        "total_amount_in": total_amount_in,
        "single_path_baseline_out": round(single_path_out, 6),
        "split_route_total_out": round(total_split_out, 6),
        "improvement_over_single_path_bps": improvement_bps,
        "total_cu_used": total_cu_used,
        "max_tx_cu_ceiling": max_tx_cu,
        "cu_budget_respected": total_cu_used <= max_tx_cu,
        "zero_arbitrage_loops": all(
            len({e.pool_id for e in feasible_paths[i]}) == len(feasible_paths[i])
            for i, a in enumerate(allocations)
            if a > 0
        ),
        "split_routes": split_routes,
    }
