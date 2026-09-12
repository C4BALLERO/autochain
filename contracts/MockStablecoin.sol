// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "@openzeppelin/contracts/token/ERC20/ERC20.sol";

/// @title MockStablecoin
/// @notice Testnet-only mock USDT/USDC-like ERC-20 (6 decimals) used to fund
///         AutoChain reward escrows during the hackathon demo. A real
///         deployment would point AutoChainReward at an existing stablecoin
///         instead of this contract. Anyone can mint, on purpose: this only
///         has value on HSK testnet.
contract MockStablecoin is ERC20 {
    constructor() ERC20("AutoChain Mock USDT", "maUSDT") {
        _mint(msg.sender, 1_000_000 * 10 ** decimals());
    }

    function decimals() public pure override returns (uint8) {
        return 6;
    }

    function mint(address to, uint256 amount) external {
        _mint(to, amount);
    }
}
