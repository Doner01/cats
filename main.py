"""
Main entry point for Koyeb, Render, Railway, and other PaaS hosting platforms.
Re-exports the Flask app instance from app.py.
"""
import os
from app import app

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
