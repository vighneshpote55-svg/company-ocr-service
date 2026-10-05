import os
import sys
from pathlib import Path

# Add project root to sys.path so tests can import modules directly
project_root = Path(__file__).parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

# Ensure DOCUMENT_ENCRYPTION_KEY is available for tests
if not os.getenv("DOCUMENT_ENCRYPTION_KEY"):
    os.environ["DOCUMENT_ENCRYPTION_KEY"] = "f4949e05975053d959987df0e8b210e0007662e69073599d21935540d5e91ea9"

if not os.getenv("JWT_SECRET"):
    os.environ["JWT_SECRET"] = "test-secret-key-for-unit-tests-only-32bytes"

import pytest

@pytest.fixture(autouse=True)
def clean_test_state():
    yield
    try:
        import main
        main.app.dependency_overrides.clear()
    except Exception:
        pass
    try:
        import ai_providers
        ai_providers.ai_provider_manager.reload_from_env()
    except Exception:
        pass



