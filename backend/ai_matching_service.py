"""
AutoChain AI Matching Service
-----------------------------
Compares a photo submitted by a collaborator ("pista") against the reference
photo(s) of a reported stolen vehicle, using CLIP image embeddings and cosine
similarity. This is intentionally simple for the hackathon MVP: no custom
training, just a pretrained model doing similarity search — which is honest,
fast to build, and easy to demo live.

Run:
    pip install fastapi uvicorn torch torchvision open_clip_torch pillow python-multipart
    uvicorn ai_matching_service:app --reload --port 8001

Tiering logic (mirrors the pitch deck's incentive table):
    score >= 0.90  -> "evidencia_clave"   (Mayor Porcentaje)
    score >= 0.75  -> "informacion_util"  (Recompensa Parcial)
    score <  0.75  -> "sin_coincidencia"
Full recovery ("recompensa_total") is confirmed manually by an operator once
the vehicle is physically recovered — it is not an AI decision.
"""

from io import BytesIO
from typing import Literal

import open_clip
import torch
from fastapi import FastAPI, File, UploadFile
from PIL import Image
from pydantic import BaseModel

app = FastAPI(title="AutoChain AI Matching Service")

device = "cuda" if torch.cuda.is_available() else "cpu"
model, _, preprocess = open_clip.create_model_and_transforms(
    "ViT-B-32", pretrained="openai"
)
model.to(device).eval()


class MatchResult(BaseModel):
    similarity: float
    tier: Literal["evidencia_clave", "informacion_util", "sin_coincidencia"]


def _embed(image_bytes: bytes) -> torch.Tensor:
    img = Image.open(BytesIO(image_bytes)).convert("RGB")
    tensor = preprocess(img).unsqueeze(0).to(device)
    with torch.no_grad():
        features = model.encode_image(tensor)
        features /= features.norm(dim=-1, keepdim=True)
    return features


def _tier_from_score(score: float) -> str:
    if score >= 0.90:
        return "evidencia_clave"
    if score >= 0.75:
        return "informacion_util"
    return "sin_coincidencia"


@app.post("/match", response_model=MatchResult)
async def match(reference_photo: UploadFile = File(...), tip_photo: UploadFile = File(...)):
    """Compare the vehicle's registered reference photo against a
    collaborator-submitted tip photo and return a similarity score + tier."""
    reference_bytes = await reference_photo.read()
    tip_bytes = await tip_photo.read()

    ref_embedding = _embed(reference_bytes)
    tip_embedding = _embed(tip_bytes)

    similarity = float((ref_embedding @ tip_embedding.T).item())
    return MatchResult(similarity=similarity, tier=_tier_from_score(similarity))


@app.get("/health")
async def health():
    return {"status": "ok", "device": device}
