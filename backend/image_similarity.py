"""
Lightweight, dependency-free (just Pillow) image similarity for AutoChain.
----------------------------------------------------------------------------
Runs directly inside the core API's serverless function — no separate model
server to deploy. This is intentionally simpler than the CLIP-based
`ai_matching_service.py`: it combines a perceptual hash (captures rough
shape/structure at low resolution) with an RGB color-histogram correlation
(captures the vehicle's color, a strong signal on its own). It won't catch
subtle semantic similarity the way CLIP embeddings would, but it's honest,
runs everywhere, and gives a real score instead of none at all.

Roadmap: replace with the CLIP service (see backend/modal_app.py) once it's
deployed — the threshold-based tiering in main.py stays the same either way.
"""

from io import BytesIO

from PIL import Image

HASH_SIZE = 16  # 16x16 perceptual hash


def _perceptual_hash(image: Image.Image) -> int:
    gray = image.convert("L").resize((HASH_SIZE, HASH_SIZE), Image.LANCZOS)
    pixels = list(gray.getdata())
    avg = sum(pixels) / len(pixels)
    bits = 0
    for i, p in enumerate(pixels):
        if p > avg:
            bits |= 1 << i
    return bits


def _hash_similarity(h1: int, h2: int) -> float:
    total_bits = HASH_SIZE * HASH_SIZE
    hamming = bin(h1 ^ h2).count("1")
    return 1 - (hamming / total_bits)


def _color_histogram(image: Image.Image, bins: int = 16) -> list[float]:
    rgb = image.convert("RGB").resize((128, 128))
    hist = rgb.histogram()  # 256 bins per channel, concatenated R,G,B
    # Downsample 256 -> `bins` per channel to reduce noise from exact pixel values.
    channels = [hist[i : i + 256] for i in (0, 256, 512)]
    reduced = []
    step = 256 // bins
    for channel in channels:
        reduced.extend(sum(channel[i : i + step]) for i in range(0, 256, step))
    total = sum(reduced) or 1
    return [v / total for v in reduced]


def _histogram_similarity(h1: list[float], h2: list[float]) -> float:
    # Histogram intersection: sum of the min of each bin, a standard,
    # bounded (0..1) measure of how much two color distributions overlap.
    return sum(min(a, b) for a, b in zip(h1, h2))


def compute_similarity(reference_bytes: bytes, tip_bytes: bytes) -> float:
    ref_img = Image.open(BytesIO(reference_bytes))
    tip_img = Image.open(BytesIO(tip_bytes))

    hash_sim = _hash_similarity(_perceptual_hash(ref_img), _perceptual_hash(tip_img))
    hist_sim = _histogram_similarity(_color_histogram(ref_img), _color_histogram(tip_img))

    # Color carries a lot of signal for "is this the same car" at this level
    # of sophistication (matches the reward table's own emphasis on color as
    # a distinguishing feature), so it's weighted slightly higher than shape.
    return round(0.45 * hash_sim + 0.55 * hist_sim, 4)
