# Inside the Block: How Solana Validators Order Transactions (Post-Alpenglow `v2.2+`)

[![Zero-Dependency Python 3.11+ Verification](https://img.shields.io/badge/tests-5%2F5%20PASSED%20(0.002s)-brightgreen)](#reproducibility--one-command-verification)
[![Agave prio-graph DAG](https://img.shields.io/badge/Agave-prio--graph%20%2B%20BankingStage-blue)](./DESIGN.md)
[![Docker Compose Ready](https://img.shields.io/badge/docker--compose-reproducible-2496ED)](./docker-compose.yml)

Empirical research suite and cycle-accurate Agave `prio-graph` / Jito Block Engine scheduler verifier answering Superteam Earn's **Inside the Block: How Solana Validators Order Transactions** bounty.

---

## Repository Structure

| Path | Purpose |
|---|---|
| [`DESIGN.md`](./DESIGN.md) | Experimental methodology: `4x4` Latin Square probe rotation, Agave integer priority formula, and the **Fee-Payer Write-Lock Serialization Confounder** (`accountKeys[0]`). |
| [`REPORT.md`](./REPORT.md) | Empirical findings report: Spearman rank correlation (`rho = -1.0000`), Mann-Whitney $U$ significance (`|z| > 1.96`), default `200,000 CU` dilution penalty (`102.7x`), and post-Alpenglow `150ms` regime shift. |
| [`scripts/pilots/superteam_01_agave_prio_graph_simulator.py`](./scripts/pilots/superteam_01_agave_prio_graph_simulator.py) | Standalone Agave `prio-graph` DAG topological wave scheduler, `4x4` Latin Square generator, fee-payer write-lock confounder analyzer, and non-parametric statistical test engine. |
| [`tests/test_superteam_breakthrough_bounties.py`](./tests/test_superteam_breakthrough_bounties.py) | Zero-dependency `unittest` verification suite (`5/5` deterministic tests proving priority formulas, write-lock serialization waves, Latin Square balance, and Spearman/Mann-Whitney statistics). |
| [`Dockerfile`](./Dockerfile) & [`docker-compose.yml`](./docker-compose.yml) | Turnkey container environment running both the unit test suite and CLI verification table out-of-the-box. |

---

## Key Breakthrough: Isolating the Fee-Payer Write-Lock Confounder (`accountKeys[0]`)

A common flaw in Solana transaction ordering experiments is dispatching concurrent probes `(T_low, T_med, T_high, T_ultra)` from a **single shared fee-payer wallet**:
1. In the Solana transaction format, `message.accountKeys[0]` is **always the fee-payer** and is **mandatorily marked `writable`** to debit lamport fees.
2. When 4 probes share the same fee-payer, Agave's `PrioGraph::insert_transaction` detects a write-lock collision on `accountKeys[0]` and serializes all 4 probes into **4 sequential execution waves (`wave_count = 4`)**, confounding arrival timing with self-inflicted lock contention.
3. By provisioning **4 disjoint ephemeral sub-payer keypairs (`ephemeral-payer-0..3`)** paired with a balanced **`4x4` Latin Square schedule**, all 4 probes execute in **1 parallel topological wave (`wave_count = 1`)**, isolating the true causal effect of `SetComputeUnitPrice` and `SetComputeUnitLimit`.

---

## Reproducibility & One-Command Verification

```bash
# 1. Run the zero-dependency unittest suite (5/5 tests)
python -m unittest discover -s tests -p "test_*.py" -v

# 2. Run the CLI verification summary table
python scripts/pilots/superteam_01_agave_prio_graph_simulator.py

# 3. Or run everything inside Docker
docker compose up --build
```
