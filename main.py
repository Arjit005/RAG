"""
Root ASGI Entrypoint for Render / Production Deployments.
Forwards cleanly to the enterprise application in src.rag.api:app.
"""

import os
import sys

# Memory optimizations for constrained environments (e.g. Render Free 512MB RAM)
os.environ["TORCH_NUM_THREADS"] = "1"
os.environ["OMP_NUM_THREADS"] = "1"
os.environ["MALLOC_ARENA_MAX"] = "2"
os.environ["TOKENIZERS_PARALLELISM"] = "false"

from src.rag.api import app

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("main:app", host="0.0.0.0", port=port)
