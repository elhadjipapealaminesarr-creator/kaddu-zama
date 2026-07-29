const { expect } = require("chai");
const { ethers, fhevm } = require("hardhat");

// Runs on the fhEVM Hardhat mock (local): `npx hardhat test`
// Helper: encrypt a single uint value for (contract, sender).
async function enc64(contract, sender, value) {
  const input = await fhevm.createEncryptedInput(contract, sender.address).add64(BigInt(value)).encrypt();
  return { handle: input.handles[0], proof: input.inputProof };
}
async function enc8(contract, sender, value) {
  const input = await fhevm.createEncryptedInput(contract, sender.address).add8(Number(value)).encrypt();
  return { handle: input.handles[0], proof: input.inputProof };
}

describe("KadduTender", function () {
  let tender, token, tenderAddr, tokenAddr;
  let org, val1, val2, val3, b1, b2, b3;
  const RESERVE = 1000n;
  const DAY = 86400;

  beforeEach(async function () {
    [org, val1, val2, val3, b1, b2, b3] = await ethers.getSigners();

    const Token = await ethers.getContractFactory("MockConfidentialToken");
    token = await Token.deploy();
    await token.waitForDeployment();
    tokenAddr = await token.getAddress();

    const Tender = await ethers.getContractFactory("KadduTender");
    tender = await Tender.deploy();
    await tender.waitForDeployment();
    tenderAddr = await tender.getAddress();

    // Fund organizer and bidders with confidential tokens.
    for (const who of [org, b1, b2, b3]) {
      const m = await enc64(tokenAddr, who, 100000);
      await token.connect(who).mint(who.address, m.handle, m.proof);
    }

    // create tender: reserve 1000, 1 day bidding, 1 day delivery window,
    // 3 validators, threshold 2 confirmations, collusion threshold 2 flags.
    await tender.connect(org).createTender(
      "Réfection école",
      "REF-2026-001",
      tokenAddr,
      RESERVE,
      DAY,
      DAY,
      [val1.address, val2.address, val3.address],
      2,
      2
    );
  });

  it("computes the winner (lowest bid) on encrypted data and reveals only that", async function () {
    // Bidders must approve the tender as operator (to pull the caution).
    for (const who of [b1, b2, b3]) {
      await token.connect(who).setOperator(tenderAddr, 2n ** 47n);
    }
    // b1 bids 900 (caution 50), b2 bids 700 (caution 50), b3 bids 800 (caution 50)
    // lowest = b2 (index 1) at 700.
    const bids = [[b1, 900], [b2, 700], [b3, 800]];
    for (const [who, price] of bids) {
      const p = await enc64(tenderAddr, who, price);
      const c = await enc64(tenderAddr, who, 50);
      await tender.connect(who).submitBid(0, p.handle, p.proof, c.handle, c.proof);
    }

    await tender.connect(org).closeBidding(0);

    const idxHandle = await tender.getEncryptedWinnerIndex(0);
    const priceHandle = await tender.getEncryptedWinningPrice(0);
    const winnerIdx = await fhevm.publicDecryptEuint(fhevm.FhevmType.euint32, idxHandle);
    const winPrice = await fhevm.publicDecryptEuint(fhevm.FhevmType.euint64, priceHandle);

    expect(winnerIdx).to.equal(1n); // b2 is bidder index 1
    expect(winPrice).to.equal(700n);
  });

  it("blocks payment until the community threshold is reached", async function () {
    for (const who of [b1, b2]) await token.connect(who).setOperator(tenderAddr, 2n ** 47n);
    for (const [who, price] of [[b1, 900], [b2, 700]]) {
      const p = await enc64(tenderAddr, who, price);
      const c = await enc64(tenderAddr, who, 50);
      await tender.connect(who).submitBid(0, p.handle, p.proof, c.handle, c.proof);
    }
    await tender.connect(org).closeBidding(0);

    // Fund escrow so a payment could be made.
    await token.connect(org).setOperator(tenderAddr, 2n ** 47n);
    const f = await enc64(tokenAddr, org, 1000);
    await tender.connect(org).fundEscrow(0, f.handle, f.proof);

    // Only one confirmation: below threshold => claim reverts.
    await tender.connect(val1).confirmDelivery(0);
    await expect(tender.connect(b2).claimPayment(0)).to.be.revertedWith("not released by community");

    // Second confirmation reaches threshold => claim succeeds.
    await tender.connect(val2).confirmDelivery(0);
    await expect(tender.connect(b2).claimPayment(0)).to.not.be.reverted;
  });

  it("rejects non-validators and the organizer bidding", async function () {
    const p = await enc64(tenderAddr, org, 500);
    const c = await enc64(tenderAddr, org, 10);
    await expect(
      tender.connect(org).submitBid(0, p.handle, p.proof, c.handle, c.proof)
    ).to.be.revertedWith("organizer cannot bid");

    await tender.connect(org).closeBidding(0);
    await expect(tender.connect(b1).confirmDelivery(0)).to.be.revertedWith("not a validator");
  });

  it("trips the collusion signal only when enough bidders flag (whistleblower protected)", async function () {
    for (const who of [b1, b2, b3]) await token.connect(who).setOperator(tenderAddr, 2n ** 47n);
    for (const who of [b1, b2, b3]) {
      const p = await enc64(tenderAddr, who, 800);
      const c = await enc64(tenderAddr, who, 50);
      await tender.connect(who).submitBid(0, p.handle, p.proof, c.handle, c.proof);
    }

    // Only ONE bidder flags => below threshold (2) => signal must be false.
    const f1 = await enc8(tenderAddr, b1, 1);
    await tender.connect(b1).flagCollusion(0, f1.handle, f1.proof);

    await tender.connect(org).closeBidding(0);
    await tender.connect(org).revealCollusion(0);
    let tripped = await fhevm.publicDecryptEbool(await tender.getCollusionTripped(0));
    expect(tripped).to.equal(false); // lone whistleblower NOT exposed
  });

  it("trips the collusion signal when two bidders flag independently", async function () {
    for (const who of [b1, b2, b3]) await token.connect(who).setOperator(tenderAddr, 2n ** 47n);
    for (const who of [b1, b2, b3]) {
      const p = await enc64(tenderAddr, who, 800);
      const c = await enc64(tenderAddr, who, 50);
      await tender.connect(who).submitBid(0, p.handle, p.proof, c.handle, c.proof);
    }
    for (const who of [b1, b2]) {
      const f = await enc8(tenderAddr, who, 1);
      await tender.connect(who).flagCollusion(0, f.handle, f.proof);
    }
    await tender.connect(org).closeBidding(0);
    await tender.connect(org).revealCollusion(0);
    const tripped = await fhevm.publicDecryptEbool(await tender.getCollusionTripped(0));
    expect(tripped).to.equal(true);
  });
});

describe("KadduBudgetVote", function () {
  let bv, addr, org, v1, v2, v3;
  const DAY = 86400;

  beforeEach(async function () {
    [org, v1, v2, v3] = await ethers.getSigners();
    const BV = await ethers.getContractFactory("KadduBudgetVote");
    bv = await BV.deploy();
    await bv.waitForDeployment();
    addr = await bv.getAddress();
    // Propose ceiling 1_000_000, quorum 2 of 3 voters.
    await bv.connect(org).createProposal("REF-2026-001", 1000000n, DAY, [v1.address, v2.address, v3.address], 2);
  });

  it("reveals only the boolean 'community approved' (secret tally)", async function () {
    // v1 yes, v2 yes, v3 no  => yes = 2 >= quorum 2 => approved.
    for (const [voter, val] of [[v1, 1], [v2, 1], [v3, 0]]) {
      const e = await fhevm.createEncryptedInput(addr, voter.address).add8(val).encrypt();
      await bv.connect(voter).vote(0, e.handles[0], e.inputProof);
    }
    await ethers.provider.send("evm_increaseTime", [DAY + 1]);
    await ethers.provider.send("evm_mine", []);
    await bv.connect(org).revealResult(0);
    const approved = await fhevm.publicDecryptEbool(await bv.getApproved(0));
    expect(approved).to.equal(true);
  });
});
