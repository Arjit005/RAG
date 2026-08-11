import os
import sys
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables from .env if present
load_dotenv()

# Add the src directory to Python path to ensure module resolution works correctly
src_path = Path(__file__).resolve().parent / "src"
if str(src_path) not in sys.path:
    sys.path.insert(0, str(src_path))
    sys.path.insert(0, str(src_path / "rag"))

# Import the FastAPI application
from rag.api import app

if __name__ == "__main__":
    import uvicorn
    # Read port from environment variable for deployment compatibility (e.g. Render, Heroku)
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=False)
