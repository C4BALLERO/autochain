"""
AutoChain Core API
------------------
Orchestrates the end-to-end flow:
  1. Reporta   - owner registers a vehicle (mock KYC) and later reports it stolen.
  2. Publica   - reference photo + key data stored.
  3. Colabora  - public users submit tip photos / info.
  4. Valida    - tip photo is sent to the AI matching service for a similarity score.
  5. Colabora  - validator calls the on-chain contract to release the tiered reward.

Persistence lives in Supabase (Postgres + Storage) via db.py — vehicles/cases/tips
are rows in Postgres, vehicle photos and ownership documents are Storage objects.
"""

import mimetypes
import os
from pathlib import Path
from typing import Optional

import httpx
from dotenv import load_dotenv
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse, Response
from pydantic import BaseModel
from web3 import Web3

import db

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

AI_SERVICE_URL = os.getenv("AI_SERVICE_URL", "http://localhost:8001/match")
RPC_URL = os.getenv("HSK_RPC_URL", "https://rpc-testnet.hskchain.net")
CONTRACT_ADDRESS = os.getenv("AUTOCHAIN_CONTRACT_ADDRESS")
VALIDATOR_PRIVATE_KEY = os.getenv("VALIDATOR_PRIVATE_KEY")
STABLECOIN_ADDRESS = os.getenv("STABLECOIN_ADDRESS")
STABLECOIN_DECIMALS = 6  # matches MockStablecoin; a real stablecoin's decimals() should be read dynamically

app = FastAPI(title="AutoChain Core API")

# Demo frontend is opened as a local file:// page, so browsers treat it as a
# cross-origin request against this API. Wide-open CORS is fine for the
# hackathon demo; a real deployment would restrict this to the actual frontend origin.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class TheftReport(BaseModel):
    vehicle_id: str
    reward_amount: float  # in stablecoin units
    theft_location: str  # place where the vehicle was stolen/last seen
    theft_description: Optional[str] = None  # free-text circumstances/details of the theft
    onchain_case_id: Optional[int] = None  # filled after reportarVehiculoRobado() tx


@app.post("/vehicles/register")
async def register_vehicle(
    owner_name: str,
    plate: str,
    doc_id_hash: str,  # mock KYC: hash of the ID doc, never the raw doc
    owner_wallet: str,  # used to list "mis denuncias" later; no real auth in this MVP
    brand: str,
    model: str,
    color: str,
    year: str,
    ruat_number: str,  # RUAT / vehicle registration number, for ownership validation
    description: Optional[str] = None,  # free-text distinctive characteristics
    reference_photos: list[UploadFile] = File(...),
    ownership_document: UploadFile = File(...),  # documento de compra-venta / proof of ownership
):
    # Videos are accepted here so the frontend can preview them alongside
    # photos before submitting, but only static images get persisted/matched
    # — the gallery views and the CLIP-based AI comparison only handle images.
    photo_bytes = []
    for photo in reference_photos:
        content = await photo.read()
        content_type = photo.content_type or "image/jpeg"
        if content_type.startswith("image/"):
            photo_bytes.append((content, content_type))
    if not photo_bytes:
        raise HTTPException(status_code=400, detail="Sube al menos una foto (los videos no se guardan todavía, solo se previsualizan).")
    ownership_doc_bytes = await ownership_document.read()

    vehicle = db.insert_vehicle({
        "owner_name": owner_name,
        "plate": plate,
        "doc_id_hash": doc_id_hash,
        "owner_wallet": owner_wallet,
        "brand": brand,
        "model": model,
        "color": color,
        "year": year,
        "ruat_number": ruat_number,
        "description": description,
        "photo_count": len(photo_bytes),
    })
    vehicle_id = vehicle["id"]

    for index, (content, content_type) in enumerate(photo_bytes):
        db.upload_vehicle_photo(vehicle_id, index, content, content_type)
    db.upload_ownership_document(
        vehicle_id, ownership_doc_bytes,
        ownership_document.content_type or "application/octet-stream",
        ownership_document.filename or "document",
    )

    return {"vehicle_id": vehicle_id, "photo_count": len(photo_bytes)}


@app.get("/vehicles/{vehicle_id}")
async def get_vehicle(vehicle_id: str):
    vehicle = db.get_vehicle(vehicle_id)
    if not vehicle:
        raise HTTPException(status_code=404, detail="vehicle not found")
    return {
        "vehicle_id": vehicle_id,
        "owner_name": vehicle["owner_name"],
        "plate": vehicle["plate"],
        "brand": vehicle["brand"],
        "model": vehicle["model"],
        "color": vehicle["color"],
        "year": vehicle["year"],
        "ruat_number": vehicle["ruat_number"],
        "description": vehicle["description"],
        "photo_count": vehicle["photo_count"],
    }


@app.get("/vehicles/{vehicle_id}/photo")
async def get_vehicle_photo(vehicle_id: str, index: int = 0):
    vehicle = db.get_vehicle(vehicle_id)
    if not vehicle or index < 0 or index >= vehicle["photo_count"]:
        raise HTTPException(status_code=404, detail="photo not found")
    return RedirectResponse(db.vehicle_photo_public_url(vehicle_id, index))


@app.get("/vehicles/{vehicle_id}/ownership-document")
async def get_ownership_document(vehicle_id: str):
    """Only meant for the validator/owner to review during a manual recovery
    confirmation — never linked from the public board (it's a KYC document,
    kept in a private Storage bucket)."""
    vehicle = db.get_vehicle(vehicle_id)
    if not vehicle:
        raise HTTPException(status_code=404, detail="vehicle not found")
    result = db.download_ownership_document(vehicle_id)
    if result is None:
        raise HTTPException(status_code=404, detail="document not found")
    content, filename = result
    content_type = mimetypes.guess_type(filename)[0] or "application/octet-stream"
    return Response(content=content, media_type=content_type)


@app.post("/cases/report-theft")
async def report_theft(payload: TheftReport):
    if not db.get_vehicle(payload.vehicle_id):
        return {"error": "vehicle not found"}

    onchain_case_id = payload.onchain_case_id
    if onchain_case_id is None and CONTRACT_ADDRESS and VALIDATOR_PRIVATE_KEY and STABLECOIN_ADDRESS:
        onchain_case_id = _open_case_onchain(payload.reward_amount)

    case = db.insert_case({
        "vehicle_id": payload.vehicle_id,
        "reward_amount": payload.reward_amount,
        "theft_location": payload.theft_location,
        "theft_description": payload.theft_description,
        "onchain_case_id": onchain_case_id,
        "status": "open",
    })
    return {"case_id": case["id"], "onchain_case_id": onchain_case_id}


def _serialize_case_row(row: dict) -> dict:
    vehicle = row["vehicles"]
    return {
        "case_id": row["id"],
        "vehicle_id": vehicle["id"],
        "plate": vehicle["plate"],
        "brand": vehicle["brand"],
        "model": vehicle["model"],
        "color": vehicle["color"],
        "year": vehicle["year"],
        "description": vehicle["description"],
        "photo_count": vehicle["photo_count"],
        "owner_name": vehicle["owner_name"],
        "owner_wallet": vehicle["owner_wallet"],
        "reward_amount": row["reward_amount"],
        "theft_location": row["theft_location"],
        "theft_description": row["theft_description"],
        "status": row["status"],
        "onchain_case_id": row["onchain_case_id"],
        "reported_at": row["reported_at"],
    }


@app.get("/cases")
async def list_cases(owner_wallet: Optional[str] = None):
    """Public board of all reported vehicles, or (with ?owner_wallet=) just the
    cases filed by that owner, for the "Mis denuncias" view. Newest first."""
    rows = db.list_cases_joined(owner_wallet)
    return [_serialize_case_row(r) for r in rows]


@app.get("/cases/{case_id}/tips")
async def list_case_tips(case_id: str):
    rows = db.list_tips_for_case(case_id)
    return [{**t, "tip_id": t["id"]} for t in rows]


@app.get("/tips/recent")
async def list_recent_tips(limit: int = 10):
    """Latest community-submitted tips across every case, newest first — for
    the "Últimos reportes" activity feed on the public board."""
    rows = db.list_recent_tips_joined(limit)
    items = []
    for t in rows:
        case = t["cases"]
        vehicle = case["vehicles"]
        items.append({
            "tip_id": t["id"],
            "case_id": case["id"],
            "plate": vehicle["plate"],
            "brand": vehicle["brand"],
            "model": vehicle["model"],
            "tier": t["tier"],
            "similarity": t["similarity"],
            "latitude": t["latitude"],
            "longitude": t["longitude"],
            "location_note": t["location_note"],
            "created_at": t["created_at"],
        })
    return items


@app.post("/cases/{case_id}/tips")
async def submit_tip(
    case_id: str,
    collaborator_wallet: str = Form(...),
    tip_photos: list[UploadFile] = File(...),
    latitude: Optional[float] = Form(None),
    longitude: Optional[float] = Form(None),
    location_note: Optional[str] = Form(None),
):
    case = db.get_case(case_id)
    if not case:
        return {"error": "case not found"}
    if not Web3.is_address(collaborator_wallet):
        return {"error": "collaborator_wallet is not a valid address"}
    vehicle = db.get_vehicle(case["vehicle_id"])

    # Same rule as vehicle registration: videos are useful supporting context
    # for the person reviewing tips later, but only images go into the CLIP
    # comparison below (the AI matching service only understands images).
    tip_photo_bytes = [
        await p.read() for p in tip_photos if (p.content_type or "").startswith("image/")
    ]

    # Compare every tip photo against every reference photo (different angles
    # on both sides) and keep the single best match — the collaborator only
    # needs ONE of their shots to line up with ONE of the owner's references.
    best_result = {"similarity": 0.0, "tier": "sin_coincidencia"}
    async with httpx.AsyncClient() as client:
        for index in range(vehicle["photo_count"]):
            ref_url = db.vehicle_photo_public_url(vehicle["id"], index)
            ref_resp = await client.get(ref_url, timeout=30.0)
            ref_resp.raise_for_status()
            for tip_bytes in tip_photo_bytes:
                files = {
                    "reference_photo": ("reference.jpg", ref_resp.content, "image/jpeg"),
                    "tip_photo": ("tip.jpg", tip_bytes, "image/jpeg"),
                }
                response = await client.post(AI_SERVICE_URL, files=files, timeout=30.0)
                response.raise_for_status()
                result = response.json()
                if result["similarity"] > best_result["similarity"]:
                    best_result = result

    # Tips are scored immediately but NOT paid here: the reward only gets
    # released on-chain once the vehicle owner confirms the recovery (see
    # confirm_recovery below), so multiple collaborators' tiers can be
    # settled together at that point rather than one at a time.
    tip = db.insert_tip({
        "case_id": case_id,
        "collaborator_wallet": collaborator_wallet,
        "similarity": best_result["similarity"],
        "tier": best_result["tier"],
        "latitude": latitude,
        "longitude": longitude,
        "location_note": location_note,
        "paid": False,
    })

    return {"tip_id": tip["id"], **tip}


TIER_BPS = {"informacion_util": 1000, "evidencia_clave": 3000, "recompensa_total": 10000}


@app.post("/cases/{case_id}/confirm-recovery")
async def confirm_recovery(case_id: str, collaborator_wallet: str = Form(...)):
    """Owner confirms the vehicle was physically recovered. This releases,
    in a single step: the incremental on-chain reward for every collaborator
    whose tip is still pending (in ascending tier order), plus the final
    FullRecovery bonus to the collaborator credited with the recovery."""
    case = db.get_case(case_id)
    if not case:
        return {"error": "case not found"}

    tx_hashes = []
    if CONTRACT_ADDRESS and VALIDATOR_PRIVATE_KEY and case["onchain_case_id"] is not None:
        paid_out_bps = 0
        pending = [
            t for t in db.list_tips_for_case(case_id)
            if not t["paid"] and t["tier"] != "sin_coincidencia"
        ]
        pending.sort(key=lambda t: TIER_BPS[t["tier"]])

        for tip in pending:
            if TIER_BPS[tip["tier"]] <= paid_out_bps:
                # This case's cumulative reward already covers this tier
                # (e.g. a second tip landed at the same or a lower tier as
                # one already paid) — nothing left to release for it.
                continue
            try:
                tx_hash = _reward_tip_onchain(case, tip["collaborator_wallet"], tip["tier"])
            except Exception as exc:
                # One bad tip (e.g. a malformed wallet that slipped in, or a
                # transient RPC error) must not block payouts to everyone else.
                db.update_tip(tip["id"], {"payout_error": str(exc)})
                continue
            db.update_tip(tip["id"], {"paid": True, "tx_hash": tx_hash})
            tx_hashes.append(tx_hash)
            paid_out_bps = TIER_BPS[tip["tier"]]

        recovery_tx = _reward_tip_onchain(case, collaborator_wallet, "recompensa_total")
        tx_hashes.append(recovery_tx)

    db.update_case(case_id, {"status": "closed"})
    return {"status": "closed", "tx_hashes": tx_hashes}


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
        "name": "pagarRecompensaColaborador",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function",
    },
    {
        "inputs": [{"internalType": "uint256", "name": "totalReward", "type": "uint256"}],
        "name": "reportarVehiculoRobado",
        "outputs": [{"internalType": "uint256", "name": "caseId", "type": "uint256"}],
        "stateMutability": "nonpayable",
        "type": "function",
    },
    {
        "anonymous": False,
        "inputs": [
            {"indexed": True, "internalType": "uint256", "name": "caseId", "type": "uint256"},
            {"indexed": True, "internalType": "address", "name": "owner", "type": "address"},
            {"indexed": False, "internalType": "uint256", "name": "totalReward", "type": "uint256"},
        ],
        "name": "CasoAbierto",
        "type": "event",
    },
]

ERC20_APPROVE_ABI = [
    {
        "inputs": [
            {"internalType": "address", "name": "spender", "type": "address"},
            {"internalType": "uint256", "name": "amount", "type": "uint256"},
        ],
        "name": "approve",
        "outputs": [{"internalType": "bool", "name": "", "type": "bool"}],
        "stateMutability": "nonpayable",
        "type": "function",
    }
]


def _open_case_onchain(reward_amount: float) -> int:
    """Funds the on-chain escrow for a new case: approves the reward pool
    amount and calls openCase(). Uses the validator wallet as the funding
    account for the hackathon demo (a production deployment would have the
    vehicle owner's own wallet sign these two calls instead)."""
    w3 = Web3(Web3.HTTPProvider(RPC_URL))
    account = w3.eth.account.from_key(VALIDATOR_PRIVATE_KEY)
    amount_units = int(round(reward_amount * (10 ** STABLECOIN_DECIMALS)))

    token = w3.eth.contract(address=Web3.to_checksum_address(STABLECOIN_ADDRESS), abi=ERC20_APPROVE_ABI)
    contract = w3.eth.contract(address=Web3.to_checksum_address(CONTRACT_ADDRESS), abi=CONTRACT_ABI)

    nonce = w3.eth.get_transaction_count(account.address, "pending")
    approve_tx = token.functions.approve(CONTRACT_ADDRESS, amount_units).build_transaction(
        {"from": account.address, "nonce": nonce, "gas": 100_000}
    )
    signed = account.sign_transaction(approve_tx)
    approve_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
    w3.eth.wait_for_transaction_receipt(approve_hash)

    open_tx = contract.functions.reportarVehiculoRobado(amount_units).build_transaction(
        {"from": account.address, "nonce": nonce + 1, "gas": 200_000}
    )
    signed = account.sign_transaction(open_tx)
    open_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
    receipt = w3.eth.wait_for_transaction_receipt(open_hash)

    opened = contract.events.CasoAbierto().process_receipt(receipt)
    return opened[0]["args"]["caseId"]


def _reward_tip_onchain(case: dict, collaborator_wallet: str, tier_key: str) -> str:
    w3 = Web3(Web3.HTTPProvider(RPC_URL))
    account = w3.eth.account.from_key(VALIDATOR_PRIVATE_KEY)
    contract = w3.eth.contract(address=Web3.to_checksum_address(CONTRACT_ADDRESS), abi=CONTRACT_ABI)

    tx = contract.functions.pagarRecompensaColaborador(
        case["onchain_case_id"],
        Web3.to_checksum_address(collaborator_wallet),
        TIER_MAP[tier_key],
    ).build_transaction(
        {
            "from": account.address,
            "nonce": w3.eth.get_transaction_count(account.address, "pending"),
            "gas": 200_000,
        }
    )
    signed = account.sign_transaction(tx)
    tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
    w3.eth.wait_for_transaction_receipt(tx_hash)  # ensures the nonce is settled before any follow-up call
    return Web3.to_hex(tx_hash)


@app.get("/health")
async def health():
    return {"status": "ok"}
