# Kaddu — Confidential voting for African communities

**Truly secret, verifiable votes for associations, cooperatives, tontines, unions and community groups — powered by Zama's Fully Homomorphic Encryption (FHE).**

Each ballot is encrypted; the tally is computed **directly on the encrypted ballots** (homomorphic addition), and only the final total is ever decrypted. Nobody — not the server, not the organizer, not an attacker — can read an individual vote.

- 🌍 **Live demo:** https://kaddu-zama.onrender.com
- ▶️ **3-min video:** https://youtu.be/RUnryaEYGJM
- ⛓️ **On-chain (fhEVM) contract, deployed on Sepolia:** [`0x10cE529aA8Da56420C3A69fa535AaCBFEe20f8d5`](https://sepolia.etherscan.io/address/0x10cE529aA8Da56420C3A69fa535AaCBFEe20f8d5) — source in [`/fhevm`](./fhevm)

---

## The problem

In West Africa, communities decide together constantly — but almost never in secret. Votes happen by show of hands, on paper, or on WhatsApp, where the organizer sees every choice. This enables intimidation, vote-buying and disputed results. Kaddu brings mathematically-guaranteed ballot secrecy to these everyday decisions, in French, on low-end phones, for free.

## How it uses Zama FHE

Kaddu ships **two complementary implementations** of the same idea — *compute on encrypted data, reveal only the public total*:

1. **Live app (this repo)** — a phone-first web app (Flask) that runs a **real FHE tally in production** with Zama's **Concrete**. Ballots are encrypted, stored as ciphertext, summed homomorphically, and only the final per-option totals are decrypted.
2. **On-chain version** ([`/fhevm`](./fhevm)) — `KadduVote.sol`, built on Zama's **fhEVM** (`@fhevm/solidity`), **deployed on the Sepolia testnet**. Votes are tallied on ciphertexts on-chain (`FHE.eq` → `FHE.add`); on close, only the totals are made publicly decryptable (`FHE.makePubliclyDecryptable`). This makes the result *trustless* — even the operator cannot decrypt a ballot.

## Security model (two independent guarantees)

- **Ballot secrecy — via FHE (strong).** A ballot is encrypted the instant it is cast and is never decrypted; only the aggregate total is. This holds against the server, the organizer and outside attackers.
- **One person = one vote — via unique member links (for serious votes).** For any vote that matters, the organizer generates **one unique link per member** from the dashboard; each link can vote exactly once. For casual/open polls, a browser cookie provides a light guard only — so **for real elections, always use member links**. (Secrecy and integrity are separate concerns: FHE guarantees the first; unique links guarantee the second.)

## Beyond voting — one confidential toolkit

Secret voting is the first module of a broader confidential-civic toolkit, each solving a trust problem the same way:

- **Confidential voting** — live today.
- **Tamper-proof tontines** — rotating savings recorded immutably, amounts kept private; safe even from a dishonest manager.
- **Sealed-bid procurement** — offers stay encrypted until opening (anti-corruption).
- **Protected pooling & private comparison** — pool funds or compare sensitive figures without exposing individual values.

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
- `KADDU_CAPACITY` (default 30) sets the max voters per poll.
- Works with **SQLite** locally or **PostgreSQL** in production (set `DATABASE_URL`).

## Repository structure

```
app.py            Flask app (routes, DB, community space)
fhe_engine.py     Zama Concrete FHE tally (encrypt / sum / decrypt)
templates/        HTML pages (mobile-first)
static/           assets, service worker (PWA)
fhevm/            on-chain version: KadduVote.sol (Zama fhEVM, deployed on Sepolia)
```

## License

MIT — see [LICENSE](./LICENSE). The on-chain contract in `/fhevm` is under **BSD-3-Clause-Clear** (Zama's license), as noted in its SPDX header.

---

Built solo from Dakar, Senegal, by **El Hadji Pape Alamine Sarr** — elhadjipapealaminesarr@gmail.com
