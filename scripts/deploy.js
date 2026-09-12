const hre = require("hardhat");

async function main() {
  const stablecoinAddress = process.env.STABLECOIN_ADDRESS;
  if (!stablecoinAddress) {
    throw new Error("Set STABLECOIN_ADDRESS in your .env (a testnet ERC-20 stablecoin, e.g. a mock USDT/USDC on HSK testnet)");
  }

  const AutoChainReward = await hre.ethers.getContractFactory("AutoChainReward");
  const contract = await AutoChainReward.deploy(stablecoinAddress);
  await contract.waitForDeployment();

  console.log("AutoChainReward deployed to:", await contract.getAddress());
  console.log("Stablecoin used:", stablecoinAddress);
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
