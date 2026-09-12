"""
AutoChain Core API
------------------
Orchestrates the end-to-end flow:
  1. Reporta   - owner registers a vehicle (mock KYC) and later reports it stolen.
  2. Publica   - reference photo + key data stored.
  3. Colabora  - public users submit tip photos / info.
  4. Valida    - tip photo is sent to the AI matching service for a similarity score.
  5. Colabora  - validator calls the on-chain contract to release the tiered reward.

This file intentionally keeps storage in-memory (SQLite/Postgres would replace
this in a real deployment) so the whole loop can be demoed without extra infra.
"""

import os
import uuid
from typing import Optional

import httpx
from fastapi import FastAPI, File, Form, UploadFile
from pydantic import BaseModel
from web3 import Web3

AI_SERVICE_URL = os.getenv("AI_SERVICE_URL", "http://localhost:8001/match")
RPC_URL = os.getenv("HSK_RPC_URL", "https://rpc-testnet.hskchain.net")
CONTRACT_ADDRESS = os.getenv("AUTOCHAIN_CONTRACT_ADDRESS")
VALIDATOR_PRIVATE_KEY = os.getenv("VALIDATOR_PRIVATE_KEY")

app = FastAPI(title="AutoChain Core API")

# --- in-memory "database" for the hackathon MVP ---
vehicles: dict[str, dict] = {}
cases: dict[str, dict] = {}
tips: dict[str, dict] = {}


class VehicleRegistration(BaseModel):
    owner_name: str
    plate: str
    doc_id_hash: str  # mock KYC: hash of the ID doc, never the raw doc


class TheftReport(BaseModel):
    vehicle_id: str
    reward_amount: float  # in stablecoin units
    onchain_case_id: Optional[int] = None  # filled after openCase() tx


@app.post("/vehicles/register")
async def register_vehicle(payload: VehicleRegistration, reference_photo: UploadFile = File(...)):
    vehicle_id = str(uuid.uuid4())
    photo_bytes = await reference_photo.read()
    vehicles[vehicle_id] = {
        "owner_name": payload.owner_name,
        "plate": payload.plate,
        "doc_id_hash": payload.doc_id_hash,
        "reference_photo": photo_bytes,
    }
    return {"vehicle_id": vehicle_id}


@app.post("/cases/report-theft")
async def report_theft(payload: TheftReport):
    if payload.vehicle_id not in vehicles:
        return {"error": "vehicle not found"}
    case_id = str(uuid.uuid4())
    cases[case_id] = {
        "vehicle_id": payload.vehicle_id,
        "reward_amount": payload.reward_amount,
        "onchain_case_id": payload.onchain_case_id,
        "status": "open",
    }
    return {"case_id": case_id}


@app.post("/cases/{case_id}/tips")
async def submit_tip(case_id: str, collaborator_wallet: str = Form(...), tip_photo: UploadFile = File(...)):
    case = cases.get(case_id)
    if not case:
        return {"error": "case not found"}
    vehicle = vehicles[case["vehicle_id"]]

    tip_bytes = await tip_photo.read()

    async with httpx.AsyncClient() as client:
        files = {
            "reference_photo": ("reference.jpg", vehicle["reference_photo"], "image/jpeg"),
            "tip_photo": ("tip.jpg", tip_bytes, "image/jpeg"),
        }
        response = await client.post(AI_SERVICE_URL, files=files, timeout=30.0)
        response.raise_for_status()
        result = response.json()

    tip_id = str(uuid.uuid4())
    tips[tip_id] = {
        "case_id": case_id,
        "collaborator_wallet": collaborator_wallet,
        "similarity": result["similarity"],
        "tier": result["tier"],
        "paid": False,
    }

    if result["tier"] != "sin_coincidencia" and CONTRACT_ADDRESS and VALIDATOR_PRIVATE_KEY:
        tx_hash = _reward_tip_onchain(case, collaborator_wallet, result["tier"])
        tips[tip_id]["paid"] = True
        tips[tip_id]["tx_hash"] = tx_hash

    return {"tip_id": tip_id, **result}


@app.post("/cases/{case_id}/confirm-recovery")
async def confirm_recovery(case_id: str, collaborator_wallet: str = Form(...)):
    """Manual operator confirmation that the vehicle was physically recovered
    thanks to a given collaborator -> triggers the FullRecovery tier payout."""
    case = cases.get(case_id)
    if not case:
        return {"error": "case not found"}

    tx_hash = None
    if CONTRACT_ADDRESS and VALIDATOR_PRIVATE_KEY:
        tx_hash = _reward_tip_onchain(case, collaborator_wallet, "recompensa_total")
    case["status"] = "closed"
    return {"status": "closed", "tx_hash": tx_hash}


# --- on-chain helper -------------------------------------------------------

TIER_MAP = {
    "informacion_util": 1,   # RewardTier.PartialInfo
    "evidencia_clave": 2,    # RewardTier.KeyEvidence
    "recompensa_total": 3,   # RewardTier.FullRecovery
}

CONTRACT_ABI = [
    {
        "inputs": [
            {"internalType": "uint256", "name": "caseId", "type": "uint256"},
            {"internalType": "address", "name": "collaborator", "type": "address"},
            {"internalType": "uint8", "name": "tier", "type": "uint8"},
        ],
        "name": "rewardTip",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function",
    }
]


def _reward_tip_onchain(case: dict, collaborator_wallet: str, tier_key: str) -> str:
    w3 = Web3(Web3.HTTPProvider(RPC_URL))
    account = w3.eth.account.from_key(VALIDATOR_PRIVATE_KEY)
    contract = w3.eth.contract(address=Web3.to_checksum_address(CONTRACT_ADDRESS), abi=CONTRACT_ABI)

    tx = contract.functions.rewardTip(
        case["onchain_case_id"],
        Web3.to_checksum_address(collaborator_wallet),
        TIER_MAP[tier_key],
    ).build_transaction(
        {
            "from": account.address,
            "nonce": w3.eth.get_transaction_count(account.address),
            "gas": 200_000,
        }
    )
    signed = account.sign_transaction(tx)
    tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
    return tx_hash.hex()


@app.get("/health")
async def health():
    return {"status": "ok"}
