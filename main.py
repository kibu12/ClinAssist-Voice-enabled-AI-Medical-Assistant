"""ASGI entrypoint wrapper for running from repository root."""
from pathlib import Path
import sys

PROJECT_DIR = Path(__file__).resolve().parent
APP_DIR = PROJECT_DIR / "voice_capstone"

if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

from voice_capstone.main import app


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
