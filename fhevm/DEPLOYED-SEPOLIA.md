# Kaddu — Contrats déployés sur Sepolia (testnet Ethereum / Zama Protocol)

**Date du déploiement :** 28 juillet 2026
**Réseau :** Sepolia (chainId 11155111) — réseau de test, ETH sans valeur réelle
**Wallet déployeur :** `0x012d7E6280fF0A77f46E5a4155C614e8dF68E7A2`
**Compilation :** 12 fichiers Solidity, solc 0.8.27, viaIR + optimizer, evmVersion cancun ✅

---

## Adresses des contrats

| Contrat | Adresse | Explorateur |
|---|---|---|
| **KadduTender** (appel d'offres inviolable — offres scellées + séquestre à seuil + caution + collusion) | `0x15a12f29b69dc65Bc9d6206f0Ebcb8e624549768` | https://sepolia.etherscan.io/address/0x15a12f29b69dc65Bc9d6206f0Ebcb8e624549768 |
| **KadduBudgetVote** (budget approuvé par vote communautaire confidentiel) | `0x68B6cc4949E514930773507FB60781e0Ec1ec80f` | https://sepolia.etherscan.io/address/0x68B6cc4949E514930773507FB60781e0Ec1ec80f |
| **KadduVote** (vote confidentiel on-chain) | `0x2e53C38af76aeEE1902C6FA2A1F7AdDc269F94c7` | https://sepolia.etherscan.io/address/0x2e53C38af76aeEE1902C6FA2A1F7AdDc269F94c7 |
| **KadduTontine** (tontine inviolable + vote confidentiel interne) | `0x23E30319EfB8B19d22201778A95A0B3eC50ee311` | https://sepolia.etherscan.io/address/0x23E30319EfB8B19d22201778A95A0B3eC50ee311 |

---

## À utiliser pour la candidature Zama

- Ces contrats tournent sur le **Zama Protocol (fhEVM) sur Sepolia**, comme les projets gagnants du Developer Program.
- Point de différenciation : **KadduTender** applique l'enchère scellée confidentielle au **marché public + gouvernance communautaire** (séquestre libéré par un seuil de citoyens, caution auto-sanctionnante, détecteur de collusion) — un usage civique que même Confidential RFQ de Zama ne couvre pas.
- Colle l'adresse **KadduTender** et son lien Etherscan dans le dossier comme preuve « on-chain ».

## Sécurité
- Le `.env` (clé privée) reste **local et ignoré par git** — ne jamais le publier.
- Wallet de déploiement = compte de test, financé uniquement en Sepolia ETH gratuit.
