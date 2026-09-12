const hre = require("hardhat");

async function main() {
  const MockStablecoin = await hre.ethers.getContractFactory("MockStablecoin");
  const token = await MockStablecoin.deploy();
  await token.waitForDeployment();

  const address = await token.getAddress();
  console.log("MockStablecoin deployed to:", address);
  console.log("Copy this into STABLECOIN_ADDRESS in your .env before running deploy:hsk-testnet");
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
