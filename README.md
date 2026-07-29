# Kaddu — Confidential, verifiable civic tools for communities

[![Live demo](https://img.shields.io/badge/demo-live-brightgreen)](https://kaddu-zama.onrender.com)
[![License: AGPL-3.0](https://img.shields.io/badge/License-AGPL--3.0-0E5A4A.svg)](./LICENSE)
[![Built with Zama FHE](https://img.shields.io/badge/Built%20with-Zama%20FHE-6E56CF)](https://www.zama.ai/)
[![On-chain: Sepolia](https://img.shields.io/badge/on--chain-fhEVM%20%C2%B7%20Sepolia-2e53C3)](https://sepolia.etherscan.io/address/0x15a12f29b69dc65Bc9d6206f0Ebcb8e624549768)
[![Made in](https://img.shields.io/badge/Made%20in-Dakar%20%F0%9F%87%B8%F0%9F%87%B3-E4A24C)](#)

**Truly secret, verifiable voting — plus tamper-proof tontines, sealed-bid tenders and a threshold whistleblower vault — for associations, cooperatives, unions, tontines and community groups. Powered by Zama's Fully Homomorphic Encryption (FHE).**

Every sensitive value (ballot, amount, report) is **encrypted**; computation runs **directly on the encrypted data** (homomorphic aggregation); and **only the final result is revealed** — the organizer only ever sees the total, never an individual value. The strongest guarantee — where *not even the operator* can decrypt — is provided by the **on-chain (fhEVM)** layer, where data is encrypted client-side before it ever reaches a server.

- 🌍 **Live demo:** https://kaddu-zama.onrender.com
- ▶️ **3-min video:** https://youtu.be/RUnryaEYGJM
- 💬 **Zama forum thread:** community.zama.org — topic *“Kaddu”*

---

## The problem

In West Africa, communities decide together and manage money together constantly — but almost never in secret. Votes happen by show of hands or on social apps where the organizer sees every choice; tontine managers can divert funds; tenders get rigged; corruption is hard to report without exposing yourself. Kaddu brings **mathematically-guaranteed confidentiality and record-integrity** to these everyday situations — in French, on low-end phones, for free.

## Two layers, one idea: *compute on encrypted data, reveal only the public result*

1. **Live web app (this repo)** — a phone-first app (Flask) running a **real FHE tally in production** with Zama's **Concrete**. Ballots and sensitive data are encrypted, aggregated homomorphically, and only totals are decrypted.
2. **On-chain contracts** ([`/fhevm`](./fhevm)) — built on Zama's **fhEVM** (`@fhevm/solidity`), **deployed on the Sepolia testnet**. Computation happens on ciphertexts on-chain, making results *trustless* — even the operator cannot decrypt an individual value.

## On-chain contracts (fhEVM · Sepolia)

| Contract | Role | Address |
|---|---|---|
| ⭐ **KadduTender** | Tamper-proof public tender: sealed bids, winner computed on encrypted data, **ERC-7984** confidential-token escrow released only when N citizens confirm delivery, self-slashing confidential caution, encrypted collusion tripwire. | [`0x15a1…9768`](https://sepolia.etherscan.io/address/0x15a12f29b69dc65Bc9d6206f0Ebcb8e624549768) |
| **KadduBudgetVote** | Community-approved budget ceiling. | [`0x68B6…c80f`](https://sepolia.etherscan.io/address/0x68B6cc4949E514930773507FB60781e0Ec1ec80f) |
| **KadduVote** | Confidential on-chain voting. | [`0x2e53…F94c7`](https://sepolia.etherscan.io/address/0x2e53C38af76aeEE1902C6FA2A1F7AdDc269F94c7) |
| **KadduTontine** | Tamper-proof rotating savings + internal confidential member vote. | [`0x23E3…e311`](https://sepolia.etherscan.io/address/0x23E30319EfB8B19d22201778A95A0B3eC50ee311) |

**✓ All four contracts are source-verified on Etherscan** (readable Solidity, exact-match).

> **Why KadduTender matters:** Zama's Confidential RFQ proved sealed-bid auctions for *finance*. KadduTender makes them tamper-proof for the **public good** — the first tender where the budget is set by the community, the winner is computed by encryption, and payment is released by citizens, never by the official.

## How it uses Zama FHE

`KadduVote.sol` is built on `@fhevm/solidity` 0.11.1: `vote()` takes an encrypted `externalEuint8` choice (`FHE.fromExternal`), tallies homomorphically (`FHE.eq` → `FHE.asEuint64` → `FHE.add`), and `closePoll()` calls `FHE.makePubliclyDecryptable()` to produce a public, verifiable result **without revealing any ballot**. KadduTender computes the winning sealed bid entirely on encrypted values and settles through an ERC-7984 confidential token.

## The confidential toolkit — what's live

- **Confidential voting** — secret, verifiable community votes, with downloadable **vote receipts** and tamper-proof **result certificates** (PDF) + a verification page.
- **Restricted votes** — one unique, single-use member link per person (anonymous tokens); secrecy and one-person-one-vote are handled as separate guarantees.
- **Tamper-proof tontines** — hash-chain ledger, two-sided P2P validation (payer *“I paid”* + receiver *“I received”*), secret member votes to reorder or dissolve. **Kaddu never moves money** — it is only the impartial referee.
- **Sealed-bid tenders** — bids sealed at submission, revealed only after close + verification (anti-corruption).
- **Protected pooling & private comparator** — pool funds or compare sensitive figures via homomorphic aggregation without exposing individual values.
- **Threshold whistleblower vault** — a report only surfaces if enough people independently flag the same target; a lone whistleblower stays mathematically invisible.
- **Community space** — social-style feed, comments, likes, idea wall, per-vote discussion, forum.
- **Bilingual FR/EN**, mobile-first, visitor counter, optional accounts, free.

## Run it locally

```bash
git clone https://github.com/elhadjipapealaminesarr-creator/kaddu-zama.git
cd kaddu-zama
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt gunicorn
export APP_SECRET="a-long-random-secret"
# optional: export DATABASE_URL="postgres://..."  (defaults to local SQLite)
gunicorn -w 1 -b 0.0.0.0:7860 app:app
```
Then open http://localhost:7860.

Notes:
- The FHE engine (Concrete) compiles **lazily on first vote** and is cached, so the server boots instantly (works on small free tiers).
- Works with **SQLite** locally or **PostgreSQL** in production (set `DATABASE_URL`).

The on-chain contracts live in [`/fhevm`](./fhevm) (Hardhat project); deployment addresses are in [`fhevm/DEPLOYED-SEPOLIA.md`](./fhevm/DEPLOYED-SEPOLIA.md).

## Repository structure

```
app.py            Flask app (routes, DB, community space, SEO, legal pages)
fhe_engine.py     Zama Concrete FHE engine (encrypt / aggregate / decrypt)
templates/        HTML pages (mobile-first, bilingual FR/EN)
static/           assets, service worker (PWA), social image
fhevm/            on-chain contracts (Zama fhEVM, deployed on Sepolia):
                    KadduTender · KadduBudgetVote · KadduVote · KadduTontine
```

## License

**AGPL-3.0** — see [LICENSE](./LICENSE). Reuse, including as a hosted service, must share source under the same terms. On-chain contracts in `/fhevm` carry their own SPDX headers following Zama's conventions.

---

Built solo from **Dakar, Senegal**, by **El Hadji Pape Alamine Sarr** — elhadjipapealaminesarr@gmail.com

*Kaddu: confidentiality in the service of communities — accessible to everyone, and tamper-proof.*
