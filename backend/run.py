"""Development entry point for GridVision Flask application."""

import os
import sys
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

load_dotenv(PROJECT_ROOT / ".env")
os.environ.setdefault("COMMERCIAL_RAG_CLEAR_UPLOADS_ON_STARTUP", "true")

from app import create_app

app = create_app()

if __name__ == "__main__":
    host = os.getenv("HOST", "127.0.0.1")
    port = int(os.getenv("PORT", 5000))
    debug = os.getenv("FLASK_DEBUG", "1") == "1"
    print(f"Starting GridVision API server on http://{host}:{port}/")
    app.run(host=host, port=port, debug=debug)
