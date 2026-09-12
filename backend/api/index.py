"""
Vercel serverless entrypoint for the AutoChain core API.

Deliberately thin: it just re-exports the same FastAPI app that runs locally
(backend/main.py) so there is only one copy of the actual API logic. Vercel's
Python runtime looks for a module-level `app` (ASGI callable) in this file.
main.py has no torch/CLIP dependency itself (only ai_matching_service.py
does, kept out of this deployment via requirements-ai.txt + .vercelignore),
so it fits comfortably in a serverless function.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from main import app  # noqa: E402
