# Experimental Design & Methodology (`DESIGN.md`)

## 1. Research Objective
Empirically isolate and quantify the causal effect of:
1. **Priority Fee Rate (`ComputeBudgetInstruction::SetComputeUnitPrice` in micro-lamports per CU)**
2. **Submission Timing (`t_submit` relative to slot boundary `T_0`)**
3. **Propagation Path (Direct QUIC TPU vs. RPC Broadcast vs. Jito Block Engine Bundle)**
4. **Account Write-Lock Contention (`accountKeys[0]` Fee-Payer Serialization vs. Disjoint Sub-Payers)**

on intra-slot transaction position (`tx_index / total_slot_txs`) across Solana validators post-Alpenglow (`v2.1+` / `v2.2+` unified `BankingStage` scheduler and `prio-graph` DAG).

---

## 2. Why Single-Payer Burst Experiments Fail (`The Fee-Payer Write-Lock Confounder`)
In the Solana transaction format, `message.accountKeys[0]` is **always the fee-payer** and is **mandatorily marked `writable`** so the runtime can debit transaction fees.
- If an experimenter sends 4 concurrent probe transactions `(T_low, T_med, T_high, T_ultra)` from a **single shared fee-payer wallet**, Agave's `prio-graph` (`PrioGraph::insert_transaction`) detects a write-lock collision on `accountKeys[0]`.
- Instead of scheduling the 4 transactions in parallel or purely by priority score, `prio-graph` chains edges from whichever transaction entered the channel first or tops the heap into sequential topological waves (`wave_count = 4`).
- **Our Solution (`analyze_fee_payer_write_lock_serialization`):** We provision **4 disjoint ephemeral sub-payer keypairs** (`ephemeral-payer-0..3`) funded ahead of time. Because their `accountKeys[0]` addresses are mutually disjoint and each probe writes only to an isolated PDA state account (`pda-state-0..3`), `prio-graph` schedules all 4 probes in **1 parallel wave (`wave_count = 1`)**, isolating the true effect of priority fee and timing without self-contention.

---

## 3. Agave `prio-graph` Exact Integer Priority Formula
In Agave `core/src/banking_stage/transaction_scheduler/receive_and_buffer.rs`, validator thread priority is computed using integer division:

$$\text{Priority} = \left\lfloor \frac{\text{Reward} \times 1{,}000{,}000}{\text{Requested\_CU} + 1} \right\rfloor$$

- **Confounder Control:** All controlled probes explicitly include `SetComputeUnitLimit(1,400)` alongside `SetComputeUnitPrice(P)` instead of relying on the default `200,000 CU` allocation. Leaving CU at default `200,000` when actual execution uses `1,400 CU` inflates the denominator by `142.8x`, destroying effective priority density.

---

## 4. `4x4` Latin Square Experimental Design (`build_latin_square_probe_matrix`)
To eliminate temporal intra-slot drift (`0ms` vs `+15ms` vs `+30ms` vs `+45ms`) when comparing 4 fee tiers (`1,000`, `10,000`, `100,000`, `1,000,000` micro-lamports/CU), we rotate fee tiers across timing offsets using a balanced `4x4` Latin Square (`L(r, c) = (r + c) mod 4`):

| Round | Offset `+0ms` (`ephemeral-payer-0`) | Offset `+15ms` (`ephemeral-payer-1`) | Offset `+30ms` (`ephemeral-payer-2`) | Offset `+45ms` (`ephemeral-payer-3`) |
|---|---|---|---|---|
| **Round 0** | `1,000` uLamports/CU | `10,000` uLamports/CU | `100,000` uLamports/CU | `1,000,000` uLamports/CU |
| **Round 1** | `10,000` uLamports/CU | `100,000` uLamports/CU | `1,000,000` uLamports/CU | `1,000` uLamports/CU |
| **Round 2** | `100,000` uLamports/CU | `1,000,000` uLamports/CU | `1,000` uLamports/CU | `10,000` uLamports/CU |
| **Round 3** | `1,000,000` uLamports/CU | `1,000` uLamports/CU | `10,000` uLamports/CU | `100,000` uLamports/CU |

Each fee tier appears **exactly once** at every submission offset (`+0ms`, `+15ms`, `+30ms`, `+45ms`) and **exactly once** in each round.

---

## 5. Non-Parametric Statistical Analysis & Alpenglow Regime Boundary
Because intra-slot transaction indices (`0 .. N-1`) are bounded rank variables with right-skewed tail contention on hot DeFi accounts, parametric Pearson $r$ is invalid. We compute:
- **Normalized Intra-Slot Position:** `p_i = tx_index_i / max(1, total_slot_txs - 1)` in `[0.0, 1.0]`
- **Spearman Rank Correlation ($\rho$) with Tie-Adjusted Variance:** Quantifying monotonicity between priority score and block execution rank.
- **Mann-Whitney $U$ Two-Sample Rank-Sum Test ($z$-score):** Comparing intra-slot placement between Jito-enabled vs. vanilla Agave leaders, and between pre-Alpenglow vs. post-Alpenglow slot windows (`v2.2+` `150ms` Alpenglow finality).
