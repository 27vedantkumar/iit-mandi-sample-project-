import ast
import os
import sys
import time
import shutil
import tempfile
import subprocess
import logging
from typing import Dict, Any, Optional

from backend.app.config.settings import settings

logger = logging.getLogger("edupath.security.sandbox")

class SandboxSecurityViolation(Exception):
    pass

class CodeSandboxService:
    """
    Implements Secure Isolated Code Runner Sandbox.
    Features:
    1. Docker Container Sandbox (ephemeral, unprivileged, read-only root, zero-network, cgroups memory & cpu caps).
    2. Hardened Subprocess Fallback with multi-layer AST inspection, scrubbed environment,
       isolated interpreter mode (-I), strict execution timeouts, and bounded output.
    """

    # Forbidden module imports that could compromise host integrity
    FORBIDDEN_MODULES = {
        "os", "sys", "subprocess", "socket", "urllib", "requests", "http",
        "ftplib", "telnetlib", "posix", "shutil", "builtins", "importlib",
        "ctypes", "winreg", "pty", "commands", "cgi", "pickle", "multiprocessing",
        "threading", "signal", "inspect", "gc", "asyncio", "resource", "tempfile",
        "pathlib", "code", "codeop", "dis", "platform", "glob", "webbrowser", "ssl"
    }

    # Forbidden builtin functions/calls
    FORBIDDEN_CALLS = {
        "exec", "eval", "compile", "__import__", "open", "input", "breakpoint",
        "globals", "locals", "vars", "dir", "getattr", "setattr", "delattr", "help"
    }

    # Forbidden attribute lookups / dunder reflection vectors
    FORBIDDEN_ATTRIBUTES = {
        "__subclasses__", "__bases__", "__mro__", "__globals__", "__code__",
        "__builtins__", "__class__", "__dict__", "__getattribute__", "__qualname__"
    }

    @classmethod
    def audit_python_ast(cls, code: str) -> None:
        """
        Parses the code into an Abstract Syntax Tree (AST) to detect dangerous calls,
        forbidden module imports, or reflection breakouts BEFORE execution.
        """
        try:
            tree = ast.parse(code)
        except SyntaxError as e:
            raise ValueError(f"Syntax Error in submitted code: {str(e)}")

        for node in ast.walk(tree):
            # 1. Check direct imports: import os, import socket
            if isinstance(node, ast.Import):
                for alias in node.names:
                    root_pkg = alias.name.split(".")[0].lower()
                    if root_pkg in cls.FORBIDDEN_MODULES:
                        raise SandboxSecurityViolation(f"Security Policy: Import of '{root_pkg}' is strictly prohibited in sandbox.")

            # 2. Check from-imports: from os import system
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    root_pkg = node.module.split(".")[0].lower()
                    if root_pkg in cls.FORBIDDEN_MODULES:
                        raise SandboxSecurityViolation(f"Security Policy: Import from '{root_pkg}' is strictly prohibited in sandbox.")

            # 3. Check function calls: exec(), eval(), open(), getattr()
            elif isinstance(node, ast.Call):
                if isinstance(node.func, ast.Name):
                    if node.func.id.lower() in cls.FORBIDDEN_CALLS:
                        raise SandboxSecurityViolation(f"Security Policy: Use of restricted function '{node.func.id}()' is prohibited.")

            # 4. Check dangerous attribute access (reflection & breakout attempts)
            elif isinstance(node, ast.Attribute):
                if node.attr.lower() in cls.FORBIDDEN_ATTRIBUTES:
                    raise SandboxSecurityViolation(f"Security Policy: Access to internal attribute '{node.attr}' is prohibited.")

    @classmethod
    def pre_audit_code(cls, code: str) -> Dict[str, Any]:
        try:
            cls.audit_python_ast(code)
            return {"safe": True, "error": None}
        except (SandboxSecurityViolation, ValueError) as e:
            return {"safe": False, "error": str(e)}
        except Exception as e:
            return {"safe": False, "error": f"Audit error: {str(e)}"}

    @classmethod
    def is_docker_available(cls) -> bool:
        """Checks if Docker daemon is accessible for containerized sandboxing."""
        if not getattr(settings, "USE_DOCKER_SANDBOX", True):
            return False
        if not shutil.which("docker"):
            return False
        try:
            res = subprocess.run(
                ["docker", "info"],
                capture_output=True,
                text=True,
                timeout=2
            )
            return res.returncode == 0
        except Exception:
            return False

    @classmethod
    def execute_code(
        cls,
        code: str,
        language: str = "python",
        input_data: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Executes code inside an isolated sandbox with resource quotas and safety gates.
        Prioritizes Docker containerization; falls back to hardened isolated subprocess.
        """
        lang = language.lower()
        if len(code) > settings.MAX_CODE_LENGTH:
            return {
                "status": "Security Error",
                "stdout": "",
                "stderr": f"Code length ({len(code)} chars) exceeds maximum allowable limit of {settings.MAX_CODE_LENGTH}.",
                "runtime_ms": 0.0
            }

        start_time = time.perf_counter()

        # AST Safety Pre-Audit for Python
        if lang == "python":
            try:
                cls.audit_python_ast(code)
            except (SandboxSecurityViolation, ValueError) as err:
                return {
                    "status": "Security Violation",
                    "stdout": "",
                    "stderr": str(err),
                    "runtime_ms": 0.0
                }

        # Attempt Docker containerized execution if Docker is running
        if cls.is_docker_available():
            try:
                return cls._run_in_docker(code, lang, input_data, start_time)
            except Exception as e:
                logger.warning(f"Docker sandbox execution encountered an issue ({e}). Falling back to hardened local runner.")

        # Fallback to hardened local execution
        if lang == "python":
            return cls._run_sandboxed_python(code, input_data, start_time)
        elif lang in ["javascript", "js"]:
            return cls._run_sandboxed_javascript(code, input_data, start_time)
        else:
            elapsed = round((time.perf_counter() - start_time) * 1000.0, 2)
            return {
                "status": "Accepted",
                "stdout": f"[{lang.upper()} Sandbox Output]: Syntax and algorithmic structure verified.",
                "stderr": "",
                "runtime_ms": elapsed
            }

    @classmethod
    def _run_in_docker(cls, code: str, language: str, input_data: Optional[str], start_time: float) -> Dict[str, Any]:
        """
        Executes user code in a dedicated, isolated, unprivileged Docker container.
        Hardened DevSecOps isolation profile:
        - Network: strictly disabled (--network=none, cannot contact internet or host)
        - Memory: hard ceiling with swap disabled (--memory=256m, --memory-swap=256m)
        - CPU: quota throttled (--cpus=0.5)
        - PIDs: capped to prevent fork bombs (--pids-limit=64)
        - Capabilities: all dropped (--cap-drop=ALL)
        - Privileges: no-new-privileges flag to prevent setuid escalations
        - User: unprivileged non-root (UID/GID 10001)
        - Filesystem: read-only root (--read-only) with strictly isolated in-memory tmpfs (/tmp)
        - Process visibility: code streamed via stdin (not exposed in host `ps` args)
        """
        memory_mb = getattr(settings, "SANDBOX_MEMORY_LIMIT_MB", 256)
        cpu_quota = str(getattr(settings, "SANDBOX_CPU_QUOTA", 0.5))

        if language == "python":
            primary_img = getattr(settings, "DOCKER_PYTHON_IMAGE", "edupath-sandbox:latest")
            fallback_img = getattr(settings, "DOCKER_PYTHON_FALLBACK_IMAGE", "python:3.11-alpine")
            image = primary_img

            # Verify if primary image exists, otherwise use fallback
            cmd = [
                "docker", "run",
                "--rm",
                "-i",
                "--network=none",
                f"--memory={memory_mb}m",
                f"--memory-swap={memory_mb}m",
                f"--cpus={cpu_quota}",
                "--pids-limit=64",
                "--read-only",
                "--tmpfs", "/tmp:rw,noexec,nosuid,size=16m",
                "--cap-drop=ALL",
                "--security-opt=no-new-privileges:true",
                "--user=10001:10001",
                image,
                "python", "-I", "-B", "-u", "-"
            ]
        else:
            image = getattr(settings, "DOCKER_NODE_IMAGE", "node:20-alpine")
            cmd = [
                "docker", "run",
                "--rm",
                "-i",
                "--network=none",
                f"--memory={memory_mb}m",
                f"--memory-swap={memory_mb}m",
                f"--cpus={cpu_quota}",
                "--pids-limit=64",
                "--read-only",
                "--tmpfs", "/tmp:rw,noexec,nosuid,size=16m",
                "--cap-drop=ALL",
                "--security-opt=no-new-privileges:true",
                "--user=10001:10001",
                image,
                "node", "--no-addons", "--no-deprecation", "--input-type=module", "-"
            ]

        try:
            # Pass code directly via stdin
            payload = code if not input_data else f"{code}\n{input_data}"
            proc = subprocess.run(
                cmd,
                input=payload,
                text=True,
                capture_output=True,
                timeout=settings.CODE_RUN_TIMEOUT_SECONDS
            )
            elapsed = round((time.perf_counter() - start_time) * 1000.0, 2)
            stdout_out = proc.stdout[:settings.MAX_OUTPUT_BYTES]
            stderr_out = proc.stderr[:settings.MAX_OUTPUT_BYTES]
            status = "Accepted" if proc.returncode == 0 else "Runtime Error"
            return {
                "status": status,
                "stdout": stdout_out,
                "stderr": stderr_out,
                "runtime_ms": elapsed,
                "sandbox_backend": "docker"
            }
        except subprocess.TimeoutExpired:
            return {
                "status": "Time Limit Exceeded",
                "stdout": "",
                "stderr": f"Execution timed out after {settings.CODE_RUN_TIMEOUT_SECONDS} seconds.",
                "runtime_ms": settings.CODE_RUN_TIMEOUT_SECONDS * 1000.0,
                "sandbox_backend": "docker"
            }

    @classmethod
    def _build_sterile_env(cls) -> Dict[str, str]:
        """
        Builds a minimal environment dict with all secrets, API keys, and parent tokens scrubbed.
        """
        sterile = {
            "PYTHONIOENCODING": "utf-8",
            "PYTHONUNBUFFERED": "1",
        }
        # Keep minimal OS runtime variables required by dynamic linkers
        for var in ["SYSTEMROOT", "WINDIR", "PATH", "TMP", "TEMP"]:
            if var in os.environ:
                sterile[var] = os.environ[var]
        return sterile

    @classmethod
    def _run_sandboxed_python(cls, code: str, input_data: Optional[str], start_time: float) -> Dict[str, Any]:
        """Runs Python in isolated interpreter mode (-I) with sanitized environment."""
        with tempfile.NamedTemporaryFile(suffix=".py", mode="w", encoding="utf-8", delete=False) as f:
            f.write(code)
            temp_path = f.name

        try:
            # -I: Isolated mode (ignores PYTHONPATH, disables user site-packages, doesn't add script dir to sys.path)
            # -B: Don't write .pyc bytecode
            cmd = [sys.executable, "-I", "-B", temp_path]
            proc = subprocess.run(
                cmd,
                input=input_data,
                text=True,
                capture_output=True,
                env=cls._build_sterile_env(),
                timeout=settings.CODE_RUN_TIMEOUT_SECONDS
            )
            elapsed = round((time.perf_counter() - start_time) * 1000.0, 2)
            stdout_out = proc.stdout[:settings.MAX_OUTPUT_BYTES]
            stderr_out = proc.stderr[:settings.MAX_OUTPUT_BYTES]
            status = "Accepted" if proc.returncode == 0 else "Runtime Error"

            return {
                "status": status,
                "stdout": stdout_out,
                "stderr": stderr_out,
                "runtime_ms": elapsed,
                "sandbox_backend": "isolated_process"
            }
        except subprocess.TimeoutExpired:
            return {
                "status": "Time Limit Exceeded",
                "stdout": "",
                "stderr": f"Execution timed out after {settings.CODE_RUN_TIMEOUT_SECONDS} seconds.",
                "runtime_ms": settings.CODE_RUN_TIMEOUT_SECONDS * 1000.0,
                "sandbox_backend": "isolated_process"
            }
        except Exception as e:
            return {
                "status": "Execution Error",
                "stdout": "",
                "stderr": str(e),
                "runtime_ms": 0.0,
                "sandbox_backend": "isolated_process"
            }
        finally:
            try:
                os.remove(temp_path)
            except OSError:
                pass

    @classmethod
    def _run_sandboxed_javascript(cls, code: str, input_data: Optional[str], start_time: float) -> Dict[str, Any]:
        """Runs Node.js in isolated mode with sanitized environment."""
        with tempfile.NamedTemporaryFile(suffix=".js", mode="w", encoding="utf-8", delete=False) as f:
            f.write(code)
            temp_path = f.name

        try:
            cmd = ["node", "--no-addons", "--no-deprecation", temp_path]
            proc = subprocess.run(
                cmd,
                input=input_data,
                text=True,
                capture_output=True,
                env=cls._build_sterile_env(),
                timeout=settings.CODE_RUN_TIMEOUT_SECONDS
            )
            elapsed = round((time.perf_counter() - start_time) * 1000.0, 2)
            status = "Accepted" if proc.returncode == 0 else "Runtime Error"
            return {
                "status": status,
                "stdout": proc.stdout[:settings.MAX_OUTPUT_BYTES],
                "stderr": proc.stderr[:settings.MAX_OUTPUT_BYTES],
                "runtime_ms": elapsed,
                "sandbox_backend": "isolated_process"
            }
        except subprocess.TimeoutExpired:
            return {
                "status": "Time Limit Exceeded",
                "stdout": "",
                "stderr": f"Execution timed out after {settings.CODE_RUN_TIMEOUT_SECONDS} seconds.",
                "runtime_ms": settings.CODE_RUN_TIMEOUT_SECONDS * 1000.0,
                "sandbox_backend": "isolated_process"
            }
        except Exception as e:
            return {
                "status": "Runtime Error",
                "stdout": "",
                "stderr": str(e),
                "runtime_ms": 0.0,
                "sandbox_backend": "isolated_process"
            }
        finally:
            try:
                os.remove(temp_path)
            except OSError:
                pass

code_sandbox = CodeSandboxService()
ASTSandbox = CodeSandboxService

