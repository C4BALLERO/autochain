// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import "@openzeppelin/contracts/access/Ownable.sol";
import "@openzeppelin/contracts/utils/ReentrancyGuard.sol";

/// @title AutoChainReward
/// @notice Escrow + tiered reward contract for the AutoChain vehicle-recovery
///         protocol. A vehicle owner (or insurer) funds a case with a
///         stablecoin. Collaborators who submit useful information get paid
///         out in tiers as their contribution is validated. Validation in
///         this MVP is performed off-chain by the AutoChain AI matching
///         service and relayed on-chain by a trusted validator role; the
///         production roadmap replaces the validator with a decentralized
///         oracle / multi-sig.
contract AutoChainReward is Ownable, ReentrancyGuard {
    IERC20 public immutable stablecoin;

    enum RewardTier {
        None,          // 0 - no payout
        PartialInfo,   // 1 - "Información Útil" -> Recompensa Parcial
        KeyEvidence,   // 2 - "Evidencia Clave"   -> Mayor Porcentaje
        FullRecovery   // 3 - "Recuperación Efectiva" -> Recompensa Total
    }

    struct Case {
        address owner;          // vehicle owner who funded the case
        uint256 totalReward;    // total stablecoin locked for this case
        uint256 paidOut;        // amount already paid out
        bool closed;            // true once vehicle is recovered / case closed
    }

    // basis points paid out per tier, relative to totalReward
    mapping(RewardTier => uint16) public tierBps; // 10000 = 100%

    // caseId => Case
    mapping(uint256 => Case) public cases;
    uint256 public nextCaseId;

    // addresses allowed to confirm AI-validated tips and trigger payouts
    mapping(address => bool) public validators;

    event CasoAbierto(uint256 indexed caseId, address indexed owner, uint256 totalReward);
    event RecompensaPagada(uint256 indexed caseId, address indexed collaborator, RewardTier tier, uint256 amount);
    event CasoCerrado(uint256 indexed caseId, uint256 totalPaidOut);
    event ValidadorActualizado(address indexed validator, bool allowed);

    modifier onlyValidator() {
        require(validators[msg.sender], "AutoChain: not a validator");
        _;
    }

    constructor(address _stablecoin) Ownable(msg.sender) {
        stablecoin = IERC20(_stablecoin);

        // Cumulative targets (not standalone increments): entitled = totalReward * bps / 10000,
        // and each payout only releases the delta above what's already been paid for the case.
        // FullRecovery must stay at 10000 (100%) or the remainder of the pool would be
        // stranded in the contract forever once the case is marked closed.
        tierBps[RewardTier.PartialInfo] = 1000;   // 10% cumulative
        tierBps[RewardTier.KeyEvidence] = 3000;   // 30% cumulative
        tierBps[RewardTier.FullRecovery] = 10000; // 100% cumulative — pays whatever remains
    }

    /// @notice Vehicle owner reports the theft and deposits the full reward pool.
    function reportarVehiculoRobado(uint256 totalReward) external nonReentrant returns (uint256 caseId) {
        require(totalReward > 0, "AutoChain: reward must be > 0");
        require(stablecoin.transferFrom(msg.sender, address(this), totalReward), "AutoChain: transfer failed");

        caseId = nextCaseId++;
        cases[caseId] = Case({owner: msg.sender, totalReward: totalReward, paidOut: 0, closed: false});

        emit CasoAbierto(caseId, msg.sender, totalReward);
    }

    /// @notice Called by a validator once the off-chain AI service confirms a
    ///         collaborator's tip at a given tier. Pays out the incremental
    ///         amount for that tier immediately.
    function pagarRecompensaColaborador(uint256 caseId, address collaborator, RewardTier tier) external onlyValidator nonReentrant {
        Case storage c = cases[caseId];
        require(!c.closed, "AutoChain: case closed");
        require(tier != RewardTier.None, "AutoChain: invalid tier");

        uint256 entitled = (c.totalReward * tierBps[tier]) / 10000;
        require(entitled > c.paidOut, "AutoChain: tier already paid or lower than current payout");

        uint256 amount = entitled - c.paidOut;
        c.paidOut = entitled;

        if (tier == RewardTier.FullRecovery) {
            c.closed = true;
            emit CasoCerrado(caseId, c.paidOut);
        }

        require(stablecoin.transfer(collaborator, amount), "AutoChain: payout failed");
        emit RecompensaPagada(caseId, collaborator, tier, amount);
    }

    /// @notice Owner can reclaim any unpaid balance if a case is abandoned.
    function cancelarCaso(uint256 caseId) external nonReentrant {
        Case storage c = cases[caseId];
        require(msg.sender == c.owner || msg.sender == owner(), "AutoChain: not authorized");
        require(!c.closed, "AutoChain: already closed");

        uint256 refund = c.totalReward - c.paidOut;
        c.closed = true;
        emit CasoCerrado(caseId, c.paidOut);

        if (refund > 0) {
            require(stablecoin.transfer(c.owner, refund), "AutoChain: refund failed");
        }
    }

    function asignarValidador(address validator, bool allowed) external onlyOwner {
        validators[validator] = allowed;
        emit ValidadorActualizado(validator, allowed);
    }
}
