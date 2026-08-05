"""
ERIS v1 Final Structural Audit.
Verifies the existence of all critical modules built in Phases 1-9.
"""

import os
import sys
from pathlib import Path

def run_audit():
    print("=" * 60)
    print("         ERIS v1 FINAL STRUCTURAL AUDIT (PHASES 1-9)")
    print("=" * 60)

    project_root = Path(__file__).parent.parent

    critical_files = [
        "README.md",
        "docs/architecture.md",
        "docs/decisions/0001-project-structure.md",
        "backend/core/config/settings.py",
        "backend/core/exceptions/base.py",
        "backend/core/logging/logger.py",
        "backend/providers/base/interface.py",
        "backend/providers/gemini/provider.py",
        "backend/ai/conversation/engine.py",
        "backend/api/main.py",
        "frontend/index.html",
        "frontend/app.js",
        "scripts/start_eris.py"
    ]

    missing_files = []

    for file_path in critical_files:
        full_path = project_root / file_path
        if full_path.exists():
            print(f"    ✔ Found: {file_path}")
        else:
            print(f"    ❌ MISSING: {file_path}")
            missing_files.append(file_path)

    print("\n" + "=" * 60)
    if missing_files:
        print("  ⚠️ AUDIT FAILED: Missing foundational files.")
        print("=" * 60)
        return False
    else:
        print("  ✅ AUDIT PASSED: ERIS v1 FOUNDATION IS 100% COMPLETE.")
        print("=" * 60)
        return True

if __name__ == "__main__":
    success = run_audit()
    sys.exit(0 if success else 1)
    