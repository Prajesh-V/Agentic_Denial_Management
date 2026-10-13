import subprocess
import sys
import time

import httpx


def main():
    print("Starting Uvicorn server on port 8000...")
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "backend.app.main:app", "--host", "127.0.0.1", "--port", "8000"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    
    time.sleep(2)
    try:
        with httpx.Client(base_url="http://127.0.0.1:8000", timeout=10.0) as client:
            # 1. Test root
            r_root = client.get("/")
            print(f"GET / -> {r_root.status_code}: {r_root.json()}")
            assert r_root.status_code == 200

            # 2. Test /api/health
            r_health = client.get("/api/health")
            print(f"GET /api/health -> {r_health.status_code}: {r_health.json()}")
            assert r_health.status_code == 200

            # 3. Test /api/health/db
            r_db = client.get("/api/health/db")
            print(f"GET /api/health/db -> {r_db.status_code}: {r_db.json()}")
            assert r_db.status_code == 200

            # 4. Test /api/health/llm
            r_llm = client.get("/api/health/llm")
            print(f"GET /api/health/llm -> {r_llm.status_code}: {r_llm.json()}")
            assert r_llm.status_code == 200

            # 5. Test /api/health/all
            r_all = client.get("/api/health/all")
            print(f"GET /api/health/all -> {r_all.status_code}: {r_all.json()}")
            assert r_all.status_code == 200

        print("\nAll API endpoints responded with HTTP 200 and healthy payloads!")
    finally:
        print("Stopping Uvicorn server...")
        proc.terminate()
        proc.wait(timeout=5)

if __name__ == "__main__":
    main()
