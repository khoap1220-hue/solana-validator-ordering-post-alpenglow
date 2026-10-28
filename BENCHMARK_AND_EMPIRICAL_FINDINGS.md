# Empirical Findings & Confounding-Variable Proofs

## 1. Proof 1: Compute-Unit Overestimation Dilution (`Requested_CU` vs. `Consumed_CU`)

Agave's `ReadWriteAccountSet` and `prio-graph` scheduler prioritize transactions using:

$$\text{Priority Score} = \frac{\text{Priority Fee (micro-lamports)}}{\text{Requested Compute Units (SetComputeUnitLimit)}}$$

### Experimental Verification (`test_agave_priority_cu_overestimation_dilution_and_jito_exclusion`)
- **Transaction A (`tx_bloated_cu`):** Pays `10,000 lamports` priority fee, leaves default `Requested_CU = 200,000`, consumes `25,000 CU`.
  - Effective scheduler score: `50,000 micro-lamports / CU`.
- **Transaction B (`tx_tight_cu`):** Pays only `5,000 lamports` priority fee ($50\%$ less total fee!), sets `SetComputeUnitLimit(25,000)`, consumes `25,000 CU`.
  - Effective scheduler score: `200,000 micro-lamports / CU` (**$4\times$ higher priority**).
- **Result:** Across all 4 client versions (`4.3.2`, `26.10.4`, `26.10.5`, `4.4.0-rc.1`), `tx_tight_cu` is scheduled ahead of `tx_bloated_cu` on the same hot writable account (` Raydium_SOL_USDC`).

---

## 2. Proof 2: Write-Lock Contention Chaining in Agave `prio-graph`

When a low-CU-price transaction (`tx_low`) and a high-CU-price transaction (`tx_high`) arrive within the same BankingStage look-ahead window and both request a **write lock** on the same account (`Hot_Pool_A`), `prio-graph` inserts a directed edge `tx_high -> tx_low`, guaranteeing `tx_high` executes first even if `tx_low` arrived slightly earlier in the reverse-priority probe burst.
