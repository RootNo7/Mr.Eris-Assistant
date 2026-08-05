"""
ERIS Phase 7 Verification Script.
Validates FastAPI endpoints (Health, Session Creation, Session Retrieval) using TestClient.
"""

import sys
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent))

from fastapi.testclient import TestClient
from backend.api.main import app


def verify_phase7():
    print("=" * 60)
    print("         ERIS PHASE 7 API LAYER VERIFICATION")
    print("=" * 60)

    client = TestClient(app)

    # 1. Test GET /health
    print("\n[+] Testing GET /health...")
    res_health = client.get("/health")
    if res_health.status_code == 200:
        data = res_health.json()
        print(f"    ✔ Health Status: {data.get('status')}")
        print(f"    ✔ System Name: {data.get('system')}")
    else:
        print(f"    ❌ Health check failed: {res_health.status_code} {res_health.text}")
        return False

    # 2. Test POST /api/v1/chat/sessions
    print("\n[+] Testing POST /api/v1/chat/sessions...")
    res_create = client.post(
        "/api/v1/chat/sessions",
        json={"title": "Verification Session", "system_prompt": "Test Prompt"}
    )
    if res_create.status_code == 201:
        session_data = res_create.json()
        session_id = session_data.get("session_id")
        print(f"    ✔ Session Created | ID: {session_id[:8]}...")
        print(f"    ✔ Session Title: {session_data.get('title')}")
    else:
        print(f"    ❌ Session creation failed: {res_create.status_code} {res_create.text}")
        return False

    # 3. Test GET /api/v1/chat/sessions
    print("\n[+] Testing GET /api/v1/chat/sessions...")
    res_list = client.get("/api/v1/chat/sessions")
    if res_list.status_code == 200:
        sessions = res_list.json()
        print(f"    ✔ Active Session Count: {len(sessions)}")
    else:
        print(f"    ❌ Session listing failed: {res_list.status_code} {res_list.text}")
        return False

    print("\n" + "=" * 60)
    print("  ✅ VERIFICATION SUCCESSFUL: PHASE 7 API LAYER OPERATIONAL")
    print("=" * 60)
    return True


if __name__ == "__main__":
    success = verify_phase7()
    sys.exit(0 if success else 1)
    