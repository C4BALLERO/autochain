require("@nomicfoundation/hardhat-toolbox");
require("dotenv").config();

const PRIVATE_KEY = process.env.PRIVATE_KEY || "0x0000000000000000000000000000000000000000000000000000000000000000000000000000";

module.exports = {
  solidity: {
    version: "0.8.24",
    settings: {
      optimizer: { enabled: true, runs: 200 },
    },
  },
  networks: {
    // Fill in the real RPC/chainId from https://hskchain.net docs before deploying.
    hskTestnet: {
      url: process.env.HSK_TESTNET_RPC_URL || "https://rpc-testnet.hskchain.net",
      chainId: Number(process.env.HSK_TESTNET_CHAIN_ID || 0),
      accounts: [PRIVATE_KEY],
    },
    hskMainnet: {
      url: process.env.HSK_MAINNET_RPC_URL || "https://rpc.hskchain.net",
      chainId: Number(process.env.HSK_MAINNET_CHAIN_ID || 0),
      accounts: [PRIVATE_KEY],
    },
  },
};
