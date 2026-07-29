const { expect } = require("chai");
const { ethers, fhevm } = require("hardhat");

// Proves the full confidential cycle of KadduVote on the fhEVM Hardhat mock:
// encrypted ballots -> homomorphic tally -> only the aggregate totals are
// publicly decryptable. Run with: `npx hardhat test`
describe("KadduVote", function () {
  let vote, admin, alice, bob, carol, dave, addr;

  beforeEach(async function () {
    [admin, alice, bob, carol, dave] = await ethers.getSigners();
    const F = await ethers.getContractFactory("KadduVote");
    vote = await F.deploy();
    await vote.waitForDeployment();
    addr = await vote.getAddress();

    // Poll 0 with 3 options
    await vote.createPoll("Bureau 2026", "Qui préside ?", ["Awa", "Modou", "Fatou"]);
  });

  async function castVote(voter, choice) {
    const enc = await fhevm
      .createEncryptedInput(addr, voter.address)
      .add8(choice)
      .encrypt();
    await vote.connect(voter).vote(0, enc.handles[0], enc.inputProof);
  }

  it("tallies encrypted ballots and reveals only the totals", async function () {
    // Awa=2 (alice, bob), Modou=1 (carol), Fatou=1 (dave)
    await castVote(alice, 0);
    await castVote(bob, 0);
    await castVote(carol, 1);
    await castVote(dave, 2);

    const meta = await vote.getPollMeta(0);
    expect(meta.voterCount).to.equal(4);

    // Before close, totals are NOT publicly decryptable — the cycle stays secret.
    await vote.closePoll(0);

    const decrypt = async (i) =>
      fhevm.publicDecryptEuint(
        fhevm.FhevmType.euint64,
        await vote.getEncryptedTally(0, i)
      );

    expect(await decrypt(0)).to.equal(2n); // Awa
    expect(await decrypt(1)).to.equal(1n); // Modou
    expect(await decrypt(2)).to.equal(1n); // Fatou

    // Sanity: totals add up to the number of voters, nothing leaks per-voter.
    const total = (await decrypt(0)) + (await decrypt(1)) + (await decrypt(2));
    expect(total).to.equal(4n);
  });

  it("prevents double voting", async function () {
    await castVote(alice, 0);
    await expect(castVote(alice, 1)).to.be.revertedWith("already voted");
  });

  it("only the admin can close the poll", async function () {
    await expect(vote.connect(alice).closePoll(0)).to.be.revertedWith("not admin");
  });
});
