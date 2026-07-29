// Deploys both Kaddu confidential contracts to the configured network (Sepolia).
// Usage: npm run deploy:sepolia
const hre = require("hardhat");

async function main() {
  const [deployer] = await hre.ethers.getSigners();
  console.log("Deployer:", deployer.address);
  const bal = await hre.ethers.provider.getBalance(deployer.address);
  console.log("Balance :", hre.ethers.formatEther(bal), "ETH");

  const Vote = await hre.ethers.getContractFactory("KadduVote");
  const vote = await Vote.deploy();
  await vote.waitForDeployment();
  console.log("KadduVote    deployed at:", await vote.getAddress());

  const Tontine = await hre.ethers.getContractFactory("KadduTontine");
  const tontine = await Tontine.deploy();
  await tontine.waitForDeployment();
  console.log("KadduTontine deployed at:", await tontine.getAddress());

  const Tender = await hre.ethers.getContractFactory("KadduTender");
  const tender = await Tender.deploy();
  await tender.waitForDeployment();
  console.log("KadduTender  deployed at:", await tender.getAddress());

  const BudgetVote = await hre.ethers.getContractFactory("KadduBudgetVote");
  const budgetVote = await BudgetVote.deploy();
  await budgetVote.waitForDeployment();
  console.log("KadduBudgetVote deployed at:", await budgetVote.getAddress());

  console.log("\nDone. Save these addresses — you'll paste them into the frontend and your submission.");
}

main().catch((e) => {
  console.error(e);
  process.exitCode = 1;
});
