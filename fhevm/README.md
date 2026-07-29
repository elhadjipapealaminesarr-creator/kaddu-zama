# Kaddu — on-chain contracts (Zama fhEVM)

Confidential smart contracts powering Kaddu's *trustless* layer, built on **Zama's fhEVM**
(`@fhevm/solidity`). Computation runs on **ciphertexts on-chain**, so — unlike the web app —
**not even the operator can decrypt** an individual value.

> This folder is a standard Hardhat project. The consumer-facing web app lives in the repository
> root (`../`) and runs a separate FHE tally with Zama's **Concrete** off-chain.

## Contracts (`contracts/`)

| Contract | What it does |
|---|---|
| **KadduVote.sol** | Confidential voting. `vote()` takes an encrypted `externalEuint8` choice; the tally is computed on ciphertexts (`FHE.eq` → `FHE.asEuint64` → `FHE.add`); `closePoll()` calls `FHE.makePubliclyDecryptable()` so anyone can verify the totals — without ever revealing a ballot. |
| **KadduTender.sol** ⭐ | Tamper-proof public tender: sealed bids, winner computed on encrypted data, **ERC-7984** confidential-token escrow released only when N citizens confirm delivery, self-slashing confidential caution, encrypted collusion tripwire. |
| **KadduBudgetVote.sol** | Community-approved budget ceiling, set by confidential vote. |
| **KadduTontine.sol** | Tamper-proof rotating savings with an internal confidential member vote (early-turn / dissolution). |
| **IConfidentialFungibleToken.sol** | Minimal ERC-7984 confidential-token interface used by the escrow. |

## Deployment (Sepolia testnet)

Deployed on the **Sepolia** testnet (Zama Protocol / fhEVM). Test tokens have no real value.

| Contract | Address |
|---|---|
| KadduTender | [`0x15a12f29b69dc65Bc9d6206f0Ebcb8e624549768`](https://sepolia.etherscan.io/address/0x15a12f29b69dc65Bc9d6206f0Ebcb8e624549768) |
| KadduBudgetVote | [`0x68B6cc4949E514930773507FB60781e0Ec1ec80f`](https://sepolia.etherscan.io/address/0x68B6cc4949E514930773507FB60781e0Ec1ec80f) |
| KadduVote | [`0x2e53C38af76aeEE1902C6FA2A1F7AdDc269F94c7`](https://sepolia.etherscan.io/address/0x2e53C38af76aeEE1902C6FA2A1F7AdDc269F94c7) |
| KadduTontine | [`0x23E30319EfB8B19d22201778A95A0B3eC50ee311`](https://sepolia.etherscan.io/address/0x23E30319EfB8B19d22201778A95A0B3eC50ee311) |

Deployer: `0x012d7E6280fF0A77f46E5a4155C614e8dF68E7A2`. Full record in [`DEPLOYED-SEPOLIA.md`](./DEPLOYED-SEPOLIA.md).

> **Address note:** KadduVote was first deployed standalone on 15 Jul 2026 (`0x10cE52…f8d5`) and
> redeployed on 28 Jul 2026 as part of the full batch. The **current canonical address is
> `0x2e53C3…94c7`**; the earlier one is superseded.

## Build & test

```bash
npm install
npx hardhat compile          # solc 0.8.27, viaIR + optimizer, evmVersion cancun
npx hardhat test             # runs the suite on the fhEVM mock
```

Status: contracts **compile without error** against `@fhevm/solidity` 0.11.1. A Hardhat test
suite is included under `test/` — `KadduVote`, `KadduTender`, `KadduTontine` — exercising the
encrypted cycle on the fhEVM mock (encrypted inputs → homomorphic aggregation → public decryption
of the aggregate only). Run `npx hardhat test` to reproduce.

## Deploy your own

Put a **test-only** private key in `.env` (`PRIVATE_KEY=0x...`, funded with free Sepolia ETH — the
`.env` is git-ignored, never commit it), then:

```bash
npx hardhat run scripts/deploy.js --network sepolia
```

## License

On-chain contracts carry `SPDX-License-Identifier: BSD-3-Clause-Clear` (Zama convention) in their
headers. The wider Kaddu project is licensed under AGPL-3.0 (see the repository root).
