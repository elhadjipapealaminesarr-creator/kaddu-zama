# Kaddu fhEVM — vote confidentiel *on-chain* (pour candidater à Zama)

Ceci est la **version blockchain** de Kaddu, construite sur le **protocole Zama (fhEVM)**.
C'est le prérequis pour candidater au **Zama Developer Program** (Builder Track).

Le smart contract **`contracts/KadduVote.sol`** est **écrit et validé** : il compile sans
erreur contre la vraie bibliothèque `@fhevm/solidity` v0.11.1 de Zama.

---

## Ce que fait le contrat

- **`createPoll(titre, question, options[])`** — crée un vote (2 à 8 choix).
- **`vote(pollId, choixChiffré, preuve)`** — chaque bulletin est **chiffré côté client** ;
  le contrat ne voit jamais le choix. Il incrémente le décompte **sur données chiffrées**
  (`FHE.eq`, `FHE.add`), 1 vote par adresse.
- **`closePoll(pollId)`** — l'organisateur clôt ; les totaux chiffrés deviennent
  **déchiffrables publiquement** (`makePubliclyDecryptable`) → résultat vérifiable par tous,
  sans jamais révéler un vote individuel.

C'est exactement l'histoire de Zama : **calculer sur des données chiffrées**, on-chain.

---

## Tout est GRATUIT (aucune dépense)

| Élément | Coût |
|---|---|
| MetaMask (wallet) | gratuit |
| Jetons de test Sepolia (faucet) | gratuit (fausse monnaie de test) |
| Déploiement sur le testnet | gratuit (payé en jetons de test) |
| GitHub + démo | gratuit |
| Programme Zama | gratuit — **c'est lui qui te paie** |

Tes $ZAMA sur Binance ne sont **pas** utilisés ici.

---

## Étapes (je te guide à chaque fois)

**1. Installer MetaMask** (5 min, ton action)
- Va sur https://metamask.io → « Download » → extension navigateur.
- Crée un wallet. **Note ta phrase secrète (12 mots) sur papier, ne la partage JAMAIS.**

**2. Ajouter le réseau de test Sepolia + jetons gratuits**
- Dans MetaMask, active « Show test networks », choisis **Sepolia**.
- Récupère des jetons gratuits sur un « faucet » (ex. https://sepoliafaucet.com ou le faucet Google Cloud).

**3. Déployer le contrat** (je génère tout)
- On part du modèle officiel **`fhevm-hardhat-template`** de Zama :
  `git clone https://github.com/zama-ai/fhevm-hardhat-template`
- On y dépose `KadduVote.sol`, on met ta clé privée de test dans `.env`, et on déploie :
  `npx hardhat deploy --network sepolia`
- Je te donnerai les commandes exactes, une par une.

**4. Mettre le code sur GitHub** (dépôt `kaddu-fhevm`) + une petite démo web.

**5. Candidater au Zama Developer Program**
- S'inscrire via https://www.zama.org/developer-hub (Guild.xyz + Discord).
- Soumettre le projet (lien GitHub + démo + description) sur le **Builder / Startup Track**.

---

## Statut

- ✅ Smart contract écrit et **compilé sans erreur** (fhEVM v0.11.1).
- ✅ **DÉPLOYÉ sur le réseau de test Sepolia** le 15/07/2026.
  - **Adresse du contrat : `0x10cE529aA8Da56420C3A69fa535AaCBFEe20f8d5`**
  - Explorateur : https://sepolia.etherscan.io/address/0x10cE529aA8Da56420C3A69fa535AaCBFEe20f8d5
  - Déployé par : `0x012d7...8E7A2`
- ⏳ À faire : mettre le code sur GitHub (dépôt `kaddu-fhevm`) → soumettre au Zama Developer Program (Builder/Startup Track) avec l'adresse ci-dessus comme preuve.

> Rappel honnête : cette version blockchain sert surtout à **décrocher le financement Zama**.
> Pour tes vrais utilisateurs (associations sur petit téléphone), la version actuelle
> `kaddu-zama` (sans wallet ni gas) reste la meilleure. Les deux coexistent très bien.
