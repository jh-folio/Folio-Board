#!/usr/bin/env python3
"""Fail-closed process supervisor for a marker-owned QA-020 package."""

from __future__ import annotations

import argparse
import ctypes
import datetime as dt
import hashlib
import json
import os
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
import uuid
from ctypes import wintypes
from pathlib import Path
from typing import Any

MARKER = ".folio-qa-owned"
EXIT_OWNERSHIP, EXIT_HEALTH, EXIT_PROCESS = 2, 3, 5


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")


def _read(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected object: {path}")
    return value


def _write(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(temp, path)


def _write_new(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "wb") as stream:
        stream.write(data)


def _under(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def _owned(path: Path) -> dict[str, Any]:
    manifest_path = path.resolve()
    manifest = _read(manifest_path)
    root = Path(str(manifest["runRoot"])).resolve()
    marker = root / MARKER
    if not marker.is_file() or Path(str(manifest["ownershipMarker"])).resolve() != marker:
        raise PermissionError("unowned run root")
    if _read(marker).get("attemptId") != manifest.get("attemptId") or not _under(manifest_path, root):
        raise PermissionError("ownership identity mismatch")
    return manifest


def process_create_time(pid: int) -> str:
    """Return a stable OS process creation identity used before every kill."""
    if os.name == "nt":
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        handle = kernel32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
        if not handle:
            raise ProcessLookupError(pid)
        creation, exit_time, kernel, user = (wintypes.FILETIME() for _ in range(4))
        try:
            if not kernel32.GetProcessTimes(
                handle, ctypes.byref(creation), ctypes.byref(exit_time), ctypes.byref(kernel), ctypes.byref(user)
            ):
                raise OSError(ctypes.get_last_error(), "GetProcessTimes")
            return str((creation.dwHighDateTime << 32) | creation.dwLowDateTime)
        finally:
            kernel32.CloseHandle(handle)
    stat = Path(f"/proc/{pid}/stat").read_text(encoding="ascii")
    return stat.rsplit(")", 1)[1].split()[19]


def compute_epoch_id(
    supervisor_pid: int, supervisor_create_time: str | int, child_pid: int,
    child_create_time: str | int, restart_count: int, started_at: str,
) -> str:
    value = "\0".join(
        map(str, (supervisor_pid, supervisor_create_time, child_pid, child_create_time, restart_count, started_at))
    )
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _canonical_hash(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _port_open(port: int) -> bool:
    with socket.socket() as client:
        client.settimeout(0.2)
        return client.connect_ex(("127.0.0.1", port)) == 0


class WindowsJob:
    """ctypes Job Object holding every child with kill-on-close semantics."""

    def __init__(self) -> None:
        self.handle: int | None = None
        if os.name != "nt":
            return

        class BASIC(ctypes.Structure):
            _fields_ = [
                ("PerProcessUserTimeLimit", ctypes.c_longlong), ("PerJobUserTimeLimit", ctypes.c_longlong),
                ("LimitFlags", wintypes.DWORD), ("MinimumWorkingSetSize", ctypes.c_size_t),
                ("MaximumWorkingSetSize", ctypes.c_size_t), ("ActiveProcessLimit", wintypes.DWORD),
                ("Affinity", ctypes.c_size_t), ("PriorityClass", wintypes.DWORD),
                ("SchedulingClass", wintypes.DWORD),
            ]

        class IO(ctypes.Structure):
            _fields_ = [(name, ctypes.c_ulonglong) for name in (
                "ReadOperationCount", "WriteOperationCount", "OtherOperationCount",
                "ReadTransferCount", "WriteTransferCount", "OtherTransferCount",
            )]

        class EXTENDED(ctypes.Structure):
            _fields_ = [
                ("BasicLimitInformation", BASIC), ("IoInfo", IO),
                ("ProcessMemoryLimit", ctypes.c_size_t), ("JobMemoryLimit", ctypes.c_size_t),
                ("PeakProcessMemoryUsed", ctypes.c_size_t), ("PeakJobMemoryUsed", ctypes.c_size_t),
            ]

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        handle = kernel32.CreateJobObjectW(None, None)
        if not handle:
            raise OSError(ctypes.get_last_error(), "CreateJobObjectW")
        info = EXTENDED()
        info.BasicLimitInformation.LimitFlags = 0x00002000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        if not kernel32.SetInformationJobObject(handle, 9, ctypes.byref(info), ctypes.sizeof(info)):
            kernel32.CloseHandle(handle)
            raise OSError(ctypes.get_last_error(), "SetInformationJobObject")
        self.handle = handle

    def assign(self, child: subprocess.Popen[bytes]) -> None:
        if self.handle is None:
            return
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        if not kernel32.AssignProcessToJobObject(self.handle, wintypes.HANDLE(int(child._handle))):
            raise OSError(ctypes.get_last_error(), "AssignProcessToJobObject")

    def close(self) -> None:
        if self.handle is not None:
            ctypes.WinDLL("kernel32", use_last_error=True).CloseHandle(self.handle)
            self.handle = None


def _terminate(child: subprocess.Popen[bytes], expected_create_time: str) -> None:
    if child.poll() is not None:
        return
    if process_create_time(child.pid) != expected_create_time:
        raise RuntimeError("pid create-time mismatch; refusing termination")
    if os.name == "nt":
        subprocess.run(["taskkill", "/PID", str(child.pid), "/T", "/F"], capture_output=True, timeout=8, check=False)
    else:
        os.killpg(child.pid, 15)
    try:
        child.wait(timeout=8)
    except subprocess.TimeoutExpired:
        if process_create_time(child.pid) != expected_create_time:
            raise RuntimeError("pid create-time changed before forced termination")
        child.kill()
        child.wait(timeout=2)


def _health(manifest: dict[str, Any]) -> dict[str, Any] | None:
    try:
        with urllib.request.urlopen(str(manifest["urls"]["health"]), timeout=1) as response:
            value = json.loads(response.read().decode("utf-8"))
        return value if isinstance(value, dict) else None
    except (OSError, UnicodeError, json.JSONDecodeError, urllib.error.URLError):
        return None


def _wait_ready(manifest: dict[str, Any], child: subprocess.Popen[bytes], timeout: float) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    mismatch = ""
    while time.monotonic() < deadline:
        if child.poll() is not None:
            raise RuntimeError(f"child exited before ready: {child.returncode}")
        observed = _health(manifest)
        if observed is not None:
            expected = manifest["healthExpected"]
            if observed.get("workspaceIdentity") != expected.get("workspaceIdentity"):
                mismatch = "workspace mismatch"
            elif observed.get("commit") != expected.get("commit"):
                mismatch = "commit mismatch"
            elif observed.get("pid") != child.pid:
                mismatch = "pid mismatch"
            elif all(observed.get(k) == expected.get(k) for k in ("status", "version")):
                return observed
        time.sleep(0.1)
    if mismatch:
        raise IdentityError(mismatch)
    raise TimeoutError("readiness timeout")


class IdentityError(RuntimeError):
    pass


def _spawn(manifest: dict[str, Any], log: Any, job: WindowsJob) -> tuple[subprocess.Popen[bytes], str, str, list[str]]:
    root = Path(manifest["runRoot"]).resolve()
    extracted = Path(manifest["extractRoot"]).resolve()
    if not _under(extracted, root) or not (extracted / "app.py").is_file():
        raise RuntimeError("invalid extracted app root")
    launch_mode = str(manifest.get("launchMode", "app_main"))
    if launch_mode == "app_main":
        command = [sys.executable, str(extracted / "app.py")]
    elif launch_mode == "asgi_no_startup_index":
        # Normal ASGI deployment seam: imports the production FastAPI app and
        # runs its lifespan, while deliberately not invoking app.py::main()
        # (whose CLI convenience path eagerly loads/rebuilds the index).
        command = [
            sys.executable, "-m", "uvicorn", "app:fastapi_app", "--host", "127.0.0.1",
            "--port", str(manifest["port"]),
        ]
    else:
        raise RuntimeError("invalid packaged launch mode")
    env = os.environ.copy()
    env.update({
        "PORT": str(manifest["port"]), "FOLIO_HOST": "127.0.0.1",
        "FOLIO_WORKSPACE_IDENTITY": str(manifest["workspaceIdentity"]), "PYTHONUNBUFFERED": "1",
    })
    allowed_runtime_environment = {"AGENT_CLI_PROVIDER", "FOLIO_AGENT_CODEX_COMMAND"}
    runtime_environment = manifest.get("runtimeEnvironment", {})
    if not isinstance(runtime_environment, dict) or set(runtime_environment) - allowed_runtime_environment:
        raise RuntimeError("invalid runtime environment fixture keys")
    for key, value in runtime_environment.items():
        text = str(value)
        if key == "FOLIO_AGENT_CODEX_COMMAND" and not _under(Path(text).resolve(), root):
            raise RuntimeError("adapter executable is outside the owned run root")
        env[key] = text
    flags = {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP} if os.name == "nt" else {"start_new_session": True}
    started_at = _now()
    child = subprocess.Popen(
        command, cwd=extracted, env=env, stdin=subprocess.DEVNULL, stdout=log,
        stderr=subprocess.STDOUT, close_fds=True, **flags,
    )
    try:
        job.assign(child)
        created = process_create_time(child.pid)
    except BaseException:
        child.kill()
        child.wait(timeout=2)
        raise
    return child, created, started_at, command


def _server(
    supervisor_pid: int, supervisor_create_time: str, child: subprocess.Popen[bytes],
    child_create_time: str, restart_count: int, started_at: str, command: list[str],
    port: int, state: str,
) -> dict[str, Any]:
    return {
        "supervisorPid": supervisor_pid,
        "supervisorCreateTime": supervisor_create_time,
        "childPid": child.pid,
        "childCreateTime": child_create_time,
        "restartCount": restart_count,
        "epochId": compute_epoch_id(
            supervisor_pid, supervisor_create_time, child.pid, child_create_time, restart_count, started_at
        ),
        "port": port,
        "startedAt": started_at,
        "commandHash": _canonical_hash(command),
        "state": state,
    }


def run(args: argparse.Namespace) -> int:
    manifest = _owned(args.manifest)
    root, port = Path(manifest["runRoot"]), int(manifest["port"])
    server_path, control_path = root / "server.json", root / "supervisor-control.json"
    response_path, log_path = root / "supervisor-response.json", root / "server.log"
    if _port_open(port):
        raise RuntimeError("port already open")
    supervisor_pid = os.getpid()
    supervisor_create_time = process_create_time(supervisor_pid)
    restart_count = 0
    job = WindowsJob()
    with log_path.open("ab", buffering=0) as log:
        child, child_ct, started_at, command = _spawn(manifest, log, job)
        try:
            _wait_ready(manifest, child, args.readiness_timeout)
            server = _server(supervisor_pid, supervisor_create_time, child, child_ct, 0, started_at, command, port, "ready")
            _write(server_path, server)
            while True:
                if control_path.is_file():
                    try:
                        request = _read(control_path)
                    finally:
                        control_path.unlink(missing_ok=True)
                    request_id, action = str(request.get("requestId", "")), request.get("action")
                    if action == "stop":
                        _terminate(child, child_ct)
                        server["state"] = "stopped"
                        _write(server_path, server)
                        _write(response_path, {"requestId": request_id, "action": action, "completedAt": _now()})
                        return 0
                    if action == "restart":
                        triggered_at = str(request.get("createdAt", _now()))
                        old_server = dict(server)
                        old_child = {"pid": child.pid, "createTime": child_ct}
                        _terminate(child, child_ct)
                        deadline = time.monotonic() + 8
                        while _port_open(port) and time.monotonic() < deadline:
                            time.sleep(0.1)
                        if _port_open(port):
                            raise RuntimeError("port open after child termination")
                        restart_count += 1
                        child, child_ct, started_at, command = _spawn(manifest, log, job)
                        observed = _wait_ready(manifest, child, args.readiness_timeout)
                        ready_at = _now()
                        server = _server(
                            supervisor_pid, supervisor_create_time, child, child_ct,
                            restart_count, started_at, command, port, "ready",
                        )
                        if server["epochId"] == old_server["epochId"]:
                            raise RuntimeError("epoch mismatch: restart reused identity")
                        receipt = {
                            "oldEpochId": old_server["epochId"],
                            "newEpochId": server["epochId"],
                            "oldChild": old_child,
                            "newChild": {"pid": child.pid, "createTime": child_ct},
                            "triggeredAt": triggered_at,
                            "readyAt": ready_at,
                            "healthHash": _canonical_hash(observed),
                        }
                        _write_new(root / f"restart-{restart_count}-receipt.json", receipt)
                        _write(server_path, server)
                        _write(response_path, {"requestId": request_id, "action": action, "completedAt": ready_at})
                exit_code = child.poll()
                if exit_code is not None:
                    raise RuntimeError(f"owned child exited unexpectedly: {exit_code}")
                time.sleep(args.poll_interval)
        except BaseException as exc:
            try:
                _terminate(child, child_ct)
            except BaseException:
                pass
            failed = _server(
                supervisor_pid, supervisor_create_time, child, child_ct,
                restart_count, started_at, command, port, "failed",
            )
            _write(server_path, failed)
            return EXIT_HEALTH if isinstance(exc, IdentityError) else EXIT_PROCESS
        finally:
            job.close()


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description="Supervise one marker-owned packaged Folio Board server.")
    result.add_argument("--manifest", required=True, type=Path)
    result.add_argument("--readiness-timeout", type=float, default=30.0)
    result.add_argument("--poll-interval", type=float, default=0.1)
    return result


def main(argv: list[str] | None = None) -> int:
    try:
        return run(parser().parse_args(argv))
    except PermissionError as exc:
        print(f"UNOWNED_RUN_ROOT: {exc}", file=sys.stderr)
        return EXIT_OWNERSHIP
    except (KeyError, OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"SUPERVISOR_FAILED: {exc}", file=sys.stderr)
        return EXIT_PROCESS


if __name__ == "__main__":
    raise SystemExit(main())
