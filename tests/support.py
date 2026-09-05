"""Import the application without loading developer credentials or networking."""
import importlib.util
import os
import sys
from pathlib import Path
from unittest.mock import patch


def isolated_app():
    name = "catrank_test_app"
    if name not in sys.modules:
        spec = importlib.util.spec_from_file_location(name, Path(__file__).resolve().parents[1] / "app.py")
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        with patch.dict(os.environ, {"SECRET_KEY": "test-only-secret-" * 4}, clear=True), patch("dotenv.load_dotenv"):
            spec.loader.exec_module(module)
        module.app.config.update(TESTING=True)
        module.limiter.enabled = False
    return sys.modules[name]
