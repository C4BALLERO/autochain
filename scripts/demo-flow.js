const hre = require("hardhat");

async function main() {
  const stablecoinAddress = process.env.STABLECOIN_ADDRESS;
  const contractAddress = process.env.AUTOCHAIN_CONTRACT_ADDRESS;
  if (!stablecoinAddress || !contractAddress) {
    throw new Error("Set STABLECOIN_ADDRESS and AUTOCHAIN_CONTRACT_ADDRESS in your .env first");
  }

  const [signer] = await hre.ethers.getSigners();
  const token = await hre.ethers.getContractAt("MockStablecoin", stablecoinAddress);
  const reward = await hre.ethers.getContractAt("AutoChainReward", contractAddress);

  const totalReward = hre.ethers.parseUnits("100", 6); // 100 maUSDT (6 decimals)

  console.log("1) Approving AutoChainReward to spend 100 maUSDT...");
  let tx = await token.approve(contractAddress, totalReward);
  await tx.wait();
  console.log("   tx:", tx.hash);

  console.log("2) Opening case with 100 maUSDT reward pool...");
  tx = await reward.reportarVehiculoRobado(totalReward);
  const openReceipt = await tx.wait();
  console.log("   tx:", tx.hash);

  const openedEvent = openReceipt.logs
    .map((log) => {
      try {
        return reward.interface.parseLog(log);
      } catch {
        return null;
      }
    })
    .find((parsed) => parsed && parsed.name === "CasoAbierto");
  const caseId = openedEvent.args.caseId;
  console.log("   on-chain caseId:", caseId.toString());

  // Small pause: on some testnet RPC endpoints the node serving the next call
  // can briefly lag behind the block that just confirmed reportarVehiculoRobado().
  await new Promise((resolve) => setTimeout(resolve, 3000));

  console.log("3) Rewarding a tip at 'Evidencia Clave' tier (30%) to", signer.address, "...");
  tx = await reward.pagarRecompensaColaborador(caseId, signer.address, 2); // 2 = KeyEvidence
  await tx.wait();
  console.log("   tx:", tx.hash);

  console.log("\nDone. Look up any of these tx hashes on https://testnet-explorer.hsk.xyz");
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
