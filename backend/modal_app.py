"""
AutoChain AI Matching Service — Modal deployment
-------------------------------------------------
Deploys the same CLIP image-matching logic as ai_matching_service.py to
Modal (https://modal.com), so it's reachable over the public internet without
maintaining a server ourselves. Chosen after ruling out:
  - Hugging Face Spaces: Docker/Gradio SDKs now require a paid PRO plan.
  - Hugging Face Inference API: no provider currently serves CLIP/image
    feature-extraction models on the free tier (verified live).
  - Google Cloud Run: requires a GCP billing account, which wasn't usable here.
Modal's Starter plan needs no credit card and includes $30/month of free
compute — enough for this ViT-B-32 model.

One-time setup:
    pip install modal
    modal setup                    # opens a browser to link this machine to your Modal account
    modal deploy modal_app.py      # builds the image and prints the public HTTPS URL

Then point the core API at it (backend/.env or Vercel env vars):
    AI_SERVICE_URL=https://<printed-url>/match

Tiering logic (mirrors ai_matching_service.py / the pitch deck's incentive table):
    score >= 0.90  -> "evidencia_clave"   (Mayor Porcentaje)
    score >= 0.75  -> "informacion_util"  (Recompensa Parcial)
    score <  0.75  -> "sin_coincidencia"
Full recovery ("recompensa_total") is confirmed manually by an operator once
the vehicle is physically recovered — it is not an AI decision.
"""

import modal

image = modal.Image.debian_slim(python_version="3.11").pip_install(
    "fastapi[standard]==0.115.0",
    "python-multipart==0.0.9",
    "torch==2.4.1",
    "torchvision==0.19.1",
    "open_clip_torch==2.26.1",
    "pillow==10.4.0",
)

app = modal.App("autochain-ai-matching", image=image)


def _tier_from_score(score: float) -> str:
    if score >= 0.90:
        return "evidencia_clave"
    if score >= 0.75:
        return "informacion_util"
    return "sin_coincidencia"


@app.cls(image=image)
class ClipMatcher:
    @modal.enter()
    def load_model(self):
        import open_clip
        import torch

        self.torch = torch
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        self.model, _, self.preprocess = open_clip.create_model_and_transforms(
            "ViT-B-32", pretrained="openai"
        )
        self.model.to(self.device).eval()

    def _embed(self, image_bytes: bytes):
        from io import BytesIO

        from PIL import Image

        img = Image.open(BytesIO(image_bytes)).convert("RGB")
        tensor = self.preprocess(img).unsqueeze(0).to(self.device)
        with self.torch.no_grad():
            features = self.model.encode_image(tensor)
            features /= features.norm(dim=-1, keepdim=True)
        return features

    @modal.asgi_app()
    def web(self):
        from fastapi import FastAPI, File, UploadFile
        from pydantic import BaseModel

        web_app = FastAPI(title="AutoChain AI Matching Service (Modal)")

        class MatchResult(BaseModel):
            similarity: float
            tier: str

        @web_app.post("/match", response_model=MatchResult)
        async def match(reference_photo: UploadFile = File(...), tip_photo: UploadFile = File(...)):
            reference_bytes = await reference_photo.read()
            tip_bytes = await tip_photo.read()

            ref_embedding = self._embed(reference_bytes)
            tip_embedding = self._embed(tip_bytes)
            similarity = float((ref_embedding @ tip_embedding.T).item())
            return MatchResult(similarity=similarity, tier=_tier_from_score(similarity))

        @web_app.get("/health")
        async def health():
            return {"status": "ok", "device": self.device}

        return web_app
