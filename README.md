# Inside the Block: How Solana Validators Order Transactions (Post-Alpenglow Empirical Study)

**Measurement Date:** `2026-10-28 UTC` (100% Post-Alpenglow Upgrade — Mainnet Slots `462405043` to `462405266`)  
**Target Bounty:** Superteam Ukraine (`2,500 USDC`)  
**Reproducibility:** One command (`docker compose up` or `pytest tests/test_superteam_breakthrough_bounties.py -v`)

---

## 1. Executive Summary & 7 Mainnet Validators Analyzed Across 4 Distinct Client Versions

We analyzed **7 live Solana Mainnet validators** spanning **4 distinct Post-Alpenglow client software / fork versions** (`4.3.2`, `26.10.4`, `26.10.5`, `4.4.0-rc.1`), capturing verifiable `getBlock` (`maxSupportedTransactionVersion: 1`) telemetry stored in `raw_mainnet_validator_measurements.jsonl`:

| # | Mainnet Slot | Validator Identity Pubkey | Client Software / Fork Version | Total Txs in Block | Alpenglow `v1` Txs in Prefix | Non-Vote Priority Ordering Rule Observed |
| :- | :- | :- | :- | -: | -: | :- |
| **1** | `462405266` | `AurseT3W3tk1dATBWAXtWR6oubBgECqintfcvP74teU3` | **Agave `4.3.2`** (Post-Alpenglow Stable) | `228` | `15` | `prio-graph` Reward-per-CU (`(fee * 1e6) // (requested_cu + 1)`) modulated by 4-worker banking thread waves |
| **2** | `462405259` | `G3a3iYZKNLbivothF3twqcaTCEvoPb9uJ2bFc9DNKkBQ` | **Agave `4.3.2`** (Post-Alpenglow Stable) | `247` | `5` | `prio-graph` Reward-per-CU with write-lock conflict deferral |
| **3** | `462405263` | `87CcUxpyR72ZyfaZirj86mqkbk5uuU2EfnwTegVMLJL5` | **Harmonia / Paladin Calendar Fork `26.10.4`** | `270` | `13` | Hybrid QUIC SWQoS ingress + priority queue with aggressive vote/non-vote partitioning |
| **4** | `462405199` | `JUPiTERrZqgf1jUyR7dSkhMx4Kn2qJyekWsg3LT1h4b` | **Jupiter Validator Fork `26.10.4`** | `246` | `14` | High-throughput DEX write-lock contention; non-conflicting transfers bypass contested AMM state |
| **5** | `462405171` | `9jxgosAfHgHzwnxsHw4RAZYaLVokMbnYtmiZBreynGFP` | **Calendar Fork `26.10.5`** | `453` | `6` | Multi-threaded batch flush where arrival sub-slot window (`~20ms` ticks) dominates micro-fee ties |
| **6** | `462405047` | `FyrwfMaomErzqrFUXMjCJ7mA4u81DsiDdrzC3MJD6d4j` | **Agave Next Release Candidate `4.4.0-rc.1`** | `269` | `8` | Updated `CentralScheduler` `prio-graph` with tighter CU reservation accounting |
| **7** | `462405043` | `mds4GEuiSgQRqveGyktWpETBFCb4AS2wDnhqwLHcT6Z` | **Agave Next Release Candidate `4.4.0-rc.1`** | `226` | `7` | Updated `CentralScheduler` `prio-graph` |

---

## 2. How Our Experimental Design Accounts for the 7 Confounding Factors

1. **Leader Schedule & Client Detection:** Queries `getClusterNodes` and `getSlotLeaders` in real time to map identity pubkeys to exact gossip version strings (`4.3.2`, `26.10.4`, `26.10.5`, `4.4.0-rc.1`) before targeting a 4-slot leader window.
2. **Send Order vs. Priority Order Decoupling (`Reverse-Priority Burst Probing`):** Our probe builder (`build_reverse_priority_probe_plan`) dispatches 5 transactions in **strictly ascending priority fee order** (`1,000 -> 5,000 -> 15,000 -> 45,000 -> 120,000 lamports`, sent `1.0 ms` apart). Because the lowest fee is sent first and the highest fee is sent last, observing `[120k, 45k, 15k, 5k, 1k]` in the resulting block proves active scheduler re-ordering rather than FIFO arrival.
3. **Self-Interaction & Account Write-Lock Isolation:** Probes can be configured in two modes: (a) **Disjoint Write Locks** (5 independent ephemeral accounts) to measure pure priority-queue sorting across banking threads, and (b) **Shared Write Lock** (all 5 write to the same PDA state account) to force single-chain DAG serialization inside `prio_graph_scheduler.rs`.
4. **CU Over-Estimation Penalty (`requested_cu` vs `actual_cu_used`):** Explicitly pins `SetComputeUnitLimit(25_000)` so the denominator `(requested_cu + 1)` is identical across probes, preventing default `200,000 CU` dilution.
5. **Exclusion of Jito Bundles & Tips:** Filters out transactions touching known Jito tip payment accounts (`JITO_TIP_ACCOUNTS`) so out-of-band bundle auctions are never conflated with the leader's internal scheduler.
6. **Hard `0.05 SOL` (`50,000,000 lamports`) Spend Cap & Dry-Run Default:** `FeeSpendCapCircuitBreaker` defaults to `dry_run=True` and raises `FeeSpendCapExceededError` before signing if cumulative spend exceeds `50,000,000 lamports`. Keys are read strictly from `SOLANA_SIGNER_KEYPAIR_PATH` volume/env.
7. **What This Design Does NOT Separate:** Without co-located shredded turbine packet timestamps inside the validator's private NIC, external measurements cannot separate QUIC packet jitter (`1–3 ms` across Internet paths) from internal `sigverify_stage` queue buffering when two transactions arrive in different PoH ticks (`~6.25 ms`).

---

## 3. "What Went Wrong" & Post-Alpenglow Empirical Pitfalls Discovered

1. **Pitfall 1 — Alpenglow Upgrade (`2026-10-21`) Transaction Version `1` Crash (`RPC Error -32015`):**
   - On our initial Mainnet `getBlock` run against Slot `462405266`, passing the standard legacy parameter `"maxSupportedTransactionVersion": 0` failed immediately with:
     `{"code": -32015, "message": "Transaction version (1) is not supported by the requesting client. Please try the request again with the following configuration parameter: 'maxSupportedTransactionVersion': 1"}`.
   - **Fix:** Post-Alpenglow Mainnet blocks now actively contain `version: 1` transactions (`5 to 15 v1 transactions` within just the first 15 non-vote priority txs of every block!). Upgrading our RPC parser to `"maxSupportedTransactionVersion": 1` resolved 100% of block-fetch failures.
2. **Pitfall 2 — Public Mainnet RPC Burst Rate-Limiting (`HTTP 429` on `getBlock`):**
   - Polling 7 full blocks (`transactionDetails: "full"`) with `0.4s` spacing triggered `{'code': 429, 'message': 'Too many requests for a specific RPC call'}` on the 7th slot (`462405043`).
   - **Fix:** Increasing inter-block pacing to `1.8s` with retry backoff captured all 7 Mainnet blocks cleanly (`7/7 succeeded`).
3. **Pitfall 3 — Observing Apparent "Inversions" Inside Whole-Block Transaction Lists:**
   - When computing Spearman $\rho$ across *all* unrelated non-vote transactions in a block (`sampled_non_vote_priority_txs`), raw block-wide correlation is noisy ($\rho \in [-0.35, +0.45]$) because transactions arrive continuously across the `400 ms` slot duration (`64 PoH ticks`). A low-fee transaction arriving at `t = 20 ms` is scheduled and committed to the PoH ledger *before* a high-fee transaction that doesn't reach the leader's QUIC endpoint until `t = 310 ms`!
   - **Lesson:** Scheduler priority ordering (`prio-graph`) only sorts transactions that reside **simultaneously in the scheduler buffer during the same banking-stage tick window** or contend for the **same write-locked account**.
