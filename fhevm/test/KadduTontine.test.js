const { expect } = require("chai");
const { ethers, fhevm } = require("hardhat");

// Runs on the fhEVM Hardhat mock (local). `npx hardhat test`
describe("KadduTontine", function () {
  let tontine, admin, alice, bob, carol, addr;

  beforeEach(async function () {
    [admin, alice, bob, carol] = await ethers.getSigners();
    const F = await ethers.getContractFactory("KadduTontine");
    tontine = await F.deploy();
    await tontine.waitForDeployment();
    addr = await tontine.getAddress();

    await tontine.createTontine(
      "Tontine du quartier",
      1000n,
      ["Alice", "Bob", "Carol"],
      [alice.address, bob.address, carol.address]
    );
    await tontine.start(0);
  });

  it("enforces two-party validation before a cycle can advance", async function () {
    // beneficiary of cycle 1 is Alice (position 1)
    await tontine.connect(alice).confirmPayment(0);
    await tontine.connect(bob).confirmPayment(0);
    await tontine.connect(carol).confirmPayment(0);
    // not yet: beneficiary must confirm receipt
    await expect(tontine.advanceCycle(0)).to.be.revertedWith("receipt pending");
    await tontine.connect(alice).confirmReceipt(0);
    await tontine.advanceCycle(0);
    const t = await tontine.getTontine(0);
    expect(t.currentCycle).to.equal(2);
  });

  it("tallies a confidential early-turn vote without revealing individual votes", async function () {
    await tontine.connect(carol).requestEarlyTurn(0); // requestId 0

    // Alice votes YES (1), Bob votes NO (0), Carol votes YES (1)  => yesTally = 2
    for (const [voter, v] of [[alice, 1], [bob, 0], [carol, 1]]) {
      const enc = await fhevm
        .createEncryptedInput(addr, voter.address)
        .add8(v)
        .encrypt();
      await tontine
        .connect(voter)
        .voteOnRequest(0, enc.handles[0], enc.inputProof);
    }

    await tontine.closeRequest(0);

    const req = await tontine.getRequest(0);
    expect(req.voterCount).to.equal(3);

    // The aggregate is publicly decryptable; individual votes never are.
    const handle = await tontine.getEncryptedYesTally(0);
    const yes = await fhevm.publicDecryptEuint(fhevm.FhevmType.euint64, handle);
    expect(yes).to.equal(2n);
    // majority: yes*2 (4) > voterCount (3) => request passes
    expect(Number(yes) * 2 > Number(req.voterCount)).to.equal(true);
  });
});
