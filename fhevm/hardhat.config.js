require("@nomicfoundation/hardhat-toolbox");
require("@fhevm/hardhat-plugin");
require("dotenv").config();

// Deploy config is read from a .env file (never commit it):
//   SEPOLIA_RPC_URL=...   (e.g. an Infura/Alchemy Sepolia endpoint, or a public one)
//   PRIVATE_KEY=0x...     (the deployer wallet's private key — KEEP IT SECRET)

/** @type import('hardhat/config').HardhatUserConfig */
module.exports = {
  solidity: {
    version: "0.8.27",
    settings: {
      viaIR: true, // required: KadduTender has large functions (stack-too-deep otherwise)
      optimizer: { enabled: true, runs: 800 },
      evmVersion: "cancun",
    },
  },
  networks: {
    sepolia: {
      url: process.env.SEPOLIA_RPC_URL || "https://ethereum-sepolia-rpc.publicnode.com",
      accounts: process.env.PRIVATE_KEY ? [process.env.PRIVATE_KEY] : [],
      chainId: 11155111,
    },
  },
  // Source-code verification. Get a free key at https://etherscan.io/myapikey
  // and put ETHERSCAN_API_KEY=... in your .env (a single key covers Sepolia).
  etherscan: {
    apiKey: process.env.ETHERSCAN_API_KEY || "",
  },
  // Sourcify (secondary verifier) disabled — Etherscan verification is enough,
  // and Sourcify's API v1 is in a brownout. Re-enable later if you want a mirror.
  sourcify: {
    enabled: false,
  },
};
