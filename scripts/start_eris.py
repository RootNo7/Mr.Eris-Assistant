"""
ERIS End-to-End System Launcher.
Starts the FastAPI Backend and the Frontend Static Server simultaneously.
"""

import sys
import subprocess
import time
from pathlib import Path

def start_system():
    print("=" * 60)
    print("         INITIALIZING ERIS v1 END-TO-END SYSTEM")
    print("=" * 60)

    project_root = Path(__file__).parent.parent
    frontend_dir = project_root / "frontend"

    print("[1] Starting FastAPI Backend on port 8000...")
    backend_process = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "backend.api.main:app", "--host", "127.0.0.1", "--port", "8000"],
        cwd=project_root
    )

    # Give backend a second to boot
    time.sleep(2)

    print("[2] Starting Frontend Static Server on port 8080...")
    frontend_process = subprocess.Popen(
        [sys.executable, "-m", "http.server", "8080"],
        cwd=frontend_dir
    )

    print("\n" + "=" * 60)
    print("  ✅ ERIS IS ONLINE!")
    print("  -> Backend API:  http://localhost:8000/docs")
    print("  -> Frontend UI:  http://localhost:8080")
    print("=" * 60)
    print("\nPress Ctrl+C to shut down all services.")

    try:
        backend_process.wait()
    except KeyboardInterrupt:
        print("\nShutting down ERIS...")
        backend_process.terminate()
        frontend_process.terminate()
        sys.exit(0)

if __name__ == "__main__":
    start_system()
    