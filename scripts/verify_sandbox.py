import sys
from fastapi.testclient import TestClient
from backend.app.main import app
from backend.app.security.sandbox import CodeSandboxService

def run_verification():
    print("=" * 60)
    print("EDUPATH AI — SANDBOX & SECURITY VERIFICATION REPORT")
    print("=" * 60)

    client = TestClient(app)

    # 1. API Health Check
    res_health = client.get("/api/health")
    print(f"\n[1] Health Check: HTTP {res_health.status_code}")
    print(f"    Payload: {res_health.json()}")
    assert res_health.status_code == 200

    # 2. Safe User Code Execution (Algorithm verification)
    safe_code = """
def banker_simulation():
    available = [3, 3, 2]
    print(f"Simulation verified: Total available resources = {available}")
banker_simulation()
"""
    res_safe = client.post("/api/coding/run", json={"code": safe_code, "language": "python"})
    safe_json = res_safe.json()
    print(f"\n[2] Safe Code Run (/api/coding/run): HTTP {res_safe.status_code}")
    print(f"    Status: {safe_json.get('status')}")
    print(f"    Stdout: {safe_json.get('stdout', '').strip()}")
    print(f"    Runtime: {safe_json.get('runtime_ms')} ms")
    assert safe_json.get("status") == "Accepted"
    assert "Simulation verified" in safe_json.get("stdout", "")

    # 3. System Import Attack (Direct AST Pre-Audit & Endpoint Rejection)
    malicious_code = "import os; os.system('echo pwned')"
    res_malicious = client.post("/api/coding/execute", json={"code": malicious_code, "language": "python"})
    mal_json = res_malicious.json()
    print(f"\n[3] Direct OS Import Attack Block (/api/coding/execute): HTTP {res_malicious.status_code}")
    print(f"    Status: {mal_json.get('status')}")
    print(f"    Security Policy: {mal_json.get('stderr')}")
    assert mal_json.get("status") == "Security Violation"

    # 4. Socket / Network Connection Attack Block
    net_code = "import socket; s = socket.socket()"
    res_net = client.post("/api/coding/run", json={"code": net_code, "language": "python"})
    net_json = res_net.json()
    print(f"\n[4] Network Socket Attack Block: HTTP {res_net.status_code}")
    print(f"    Status: {net_json.get('status')}")
    print(f"    Security Policy: {net_json.get('stderr')}")
    assert net_json.get("status") == "Security Violation"

    # 5. Dunder Reflection / Class Hierarchy Breakout Attack
    reflection_code = "x = ().__class__.__bases__[0].__subclasses__()"
    res_refl = client.post("/api/coding/run", json={"code": reflection_code, "language": "python"})
    refl_json = res_refl.json()
    print(f"\n[5] Reflection & Subclasses Breakout Block: HTTP {res_refl.status_code}")
    print(f"    Status: {refl_json.get('status')}")
    print(f"    Security Policy: {refl_json.get('stderr')}")
    assert refl_json.get("status") == "Security Violation"

    # 6. Dangerous Builtins (open, exec, eval) Attack Block
    builtin_code = "f = open('edupath_multimodal.db', 'r')"
    res_builtin = client.post("/api/coding/run", json={"code": builtin_code, "language": "python"})
    b_json = res_builtin.json()
    print(f"\n[6] Dangerous Builtin `open()` Attack Block: HTTP {res_builtin.status_code}")
    print(f"    Status: {b_json.get('status')}")
    print(f"    Security Policy: {b_json.get('stderr')}")
    assert b_json.get("status") == "Security Violation"

    # 7. Infinite Loop Execution Timeout Check
    timeout_code = "while True:\n    pass"
    res_timeout = client.post("/api/coding/run", json={"code": timeout_code, "language": "python"})
    to_json = res_timeout.json()
    print(f"\n[7] CPU Hang / Infinite Loop Timeout: HTTP {res_timeout.status_code}")
    print(f"    Status: {to_json.get('status')}")
    print(f"    Stderr: {to_json.get('stderr')}")
    print(f"    Enforced Limit: {to_json.get('runtime_ms')} ms")
    assert to_json.get("status") == "Time Limit Exceeded"

    print("\n" + "=" * 60)
    print("ALL 7 CRITICAL SECURITY & SANDBOX VERIFICATION TESTS PASSED!")
    print("=" * 60)

if __name__ == "__main__":
    run_verification()
