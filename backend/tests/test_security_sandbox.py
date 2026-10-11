import pytest
import os
import sys
from backend.app.config.settings import settings
from backend.app.security.sandbox import CodeSandboxService, SandboxSecurityViolation

def test_secret_key_loaded_and_not_default():
    """Verify that SECRET_KEY is set and no longer uses the hardcoded default."""
    assert settings.SECRET_KEY != ""
    assert settings.SECRET_KEY != "edupath-super-secret-key-change-in-production-entropy-grade"
    assert len(settings.SECRET_KEY) >= 32

def test_cors_origins_disallows_wildcard():
    """Verify that cors_origins_list returns explicit domains and strips wildcard '*'."""
    origins = settings.cors_origins_list
    assert "*" not in origins
    assert "http://localhost:5173" in origins
    assert "http://localhost:3000" in origins

def test_sandbox_allows_safe_code():
    """Verify that benign algorithms and prints execute cleanly."""
    safe_code = """
def fibonacci(n):
    if n <= 1:
        return n
    return fibonacci(n-1) + fibonacci(n-2)

print(f"fib(7) = {fibonacci(7)}")
"""
    audit = CodeSandboxService.pre_audit_code(safe_code)
    assert audit["safe"] is True

    res = CodeSandboxService.execute_code(safe_code, language="python")
    assert res["status"] == "Accepted"
    assert "fib(7) = 13" in res["stdout"]

def test_sandbox_blocks_direct_system_imports():
    """Verify that direct imports of restricted modules are rejected at AST audit time."""
    blocked_imports = [
        "import os",
        "import sys",
        "import subprocess",
        "import socket",
        "import urllib.request",
        "import shutil",
        "import ctypes",
        "import multiprocessing",
        "import threading",
    ]
    for code in blocked_imports:
        audit = CodeSandboxService.pre_audit_code(code)
        assert audit["safe"] is False, f"Code '{code}' should have been blocked"
        
        res = CodeSandboxService.execute_code(code, language="python")
        assert res["status"] == "Security Violation"

def test_sandbox_blocks_from_imports():
    """Verify that from-imports of restricted modules are rejected."""
    blocked = [
        "from os import system",
        "from subprocess import Popen",
        "from socket import socket",
        "from shutil import rmtree",
    ]
    for code in blocked:
        audit = CodeSandboxService.pre_audit_code(code)
        assert audit["safe"] is False, f"Code '{code}' should have been blocked"

def test_sandbox_blocks_dangerous_calls_and_builtins():
    """Verify that eval, exec, open, and getattr are strictly forbidden."""
    dangerous = [
        "open('edupath_multimodal.db', 'r')",
        "eval('2 + 2')",
        "exec('x = 1')",
        "__import__('os')",
        "getattr(int, '__doc__')",
    ]
    for code in dangerous:
        audit = CodeSandboxService.pre_audit_code(code)
        assert audit["safe"] is False, f"Code '{code}' should have been blocked"

def test_sandbox_blocks_reflection_breakout_attempts():
    """Verify that dunder traversal (__subclasses__, __globals__) is caught by AST audit."""
    exploits = [
        "x = ().__class__.__bases__[0].__subclasses__()",
        "x = [].__class__.__base__.__subclasses__()",
    ]
    for code in exploits:
        audit = CodeSandboxService.pre_audit_code(code)
        assert audit["safe"] is False, f"Exploit '{code}' should have been blocked"

def test_sandbox_scrubs_parent_environment_variables():
    """Verify that sensitive parent environment variables cannot be accessed."""
    # Temporarily inject a secret into parent env
    os.environ["SUPER_SECRET_TOKEN_12345"] = "classified_database_token"
    
    # User code attempting to read os.environ (if bypassed or via other means)
    # Testing our sterile environment builder
    env = CodeSandboxService._build_sterile_env()
    assert "SUPER_SECRET_TOKEN_12345" not in env
    assert "SECRET_KEY" not in env
    assert "DATABASE_URL" not in env
    assert "OPENAI_API_KEY" not in env

def test_sandbox_enforces_execution_timeout():
    """Verify that infinite loops are killed by the timeout."""
    infinite_loop = """
while True:
    pass
"""
    res = CodeSandboxService.execute_code(infinite_loop, language="python")
    assert res["status"] == "Time Limit Exceeded"
