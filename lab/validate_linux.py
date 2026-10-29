"""Build and optionally exercise the driver in a disposable Linux guest."""

import argparse
from datetime import datetime, timezone
import gzip
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import shutil
import signal
import subprocess
import tarfile
import tempfile
import time

from .runner import ROOT, git_output, save_json

KERNEL_ERROR = re.compile(r"BUG:|WARNING:|Oops:|Kernel panic|KASAN:|KCSAN:|UBSAN:|use-after-free|invalid opcode", re.I)


def run_step(name, command, cwd, output, timeout=120, env=None):
    started = time.monotonic()
    log = output / f"{name}.log"
    result = {"name": name, "command": command, "log": log.name, "status": "failed"}
    with log.open("wb") as stream:
        try:
            process = subprocess.Popen(command, cwd=cwd, stdout=stream, stderr=subprocess.STDOUT,
                                       env=env, start_new_session=os.name == "posix")
            try:
                result["exit_code"] = process.wait(timeout=timeout)
                result["status"] = "passed" if result["exit_code"] == 0 else "failed"
            except subprocess.TimeoutExpired:
                result["status"] = "timeout"
                if os.name == "posix":
                    try:
                        os.killpg(process.pid, signal.SIGTERM)
                    except ProcessLookupError:
                        pass
                else:
                    process.terminate()
                try:
                    process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    process.kill()
                finally:
                    if os.name == "posix":
                        try:
                            os.killpg(process.pid, signal.SIGKILL)
                        except ProcessLookupError:
                            pass
                    process.wait()
                result["exit_code"] = process.returncode
        except OSError as exc:
            result["error"] = str(exc)
    result["elapsed_seconds"] = time.monotonic() - started
    return result


def new_kernel_messages(before, after):
    """Do not silently accept a rotated or inaccessible diagnostic history."""
    earlier, later = before.splitlines(), after.splitlines()
    if later[:len(earlier)] != earlier:
        return {"status": "inconclusive", "reason": "kernel log rotated or changed prefix"}
    messages = later[len(earlier):]
    findings = [line for line in messages if KERNEL_ERROR.search(line)]
    return {"status": "failed" if findings else "passed", "new_lines": len(messages), "findings": findings}


def snapshot(source, destination, files):
    """Copy the working tree, including dirty changes, without generated files."""
    records = {}
    root = source.resolve()
    for name in sorted(set(files)):
        relative = Path(name)
        if relative.is_absolute() or ".." in relative.parts:
            raise ValueError("invalid source path")
        original = source / relative
        if original.is_symlink() or not original.resolve().is_relative_to(root):
            raise ValueError(f"source symlink is not supported: {name}")
        if not original.exists():
            continue  # A tracked deletion is represented by its absence.
        if not original.is_file():
            raise ValueError(f"source is not a regular file: {name}")
        data = original.read_bytes()
        built = data.replace(b"\r\n", b"\n") if original.suffix == ".sh" else data
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(built)
        records[relative.as_posix()] = {
            "working_sha256": hashlib.sha256(data).hexdigest(),
            "build_sha256": hashlib.sha256(built).hexdigest(),
            "normalized_shell_crlf": data != built}
    return records


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True, help="new evidence directory")
    parser.add_argument("--integration", action="store_true", help="load/unload the module; disposable guest only")
    args = parser.parse_args(argv)
    output = args.output.resolve()
    try:
        output.mkdir(parents=True, exist_ok=False)
    except OSError as exc:
        parser.error(str(exc))
    manifest = {"schema_version": 1, "kind": "linux-validation", "status": "running",
                "scope": "build-and-integration" if args.integration else "build-only",
                "runtime_validated": False, "started_utc": datetime.now(timezone.utc).isoformat(),
                "platform": platform.platform(), "git_commit": git_output("rev-parse", "HEAD"),
                "git_status": git_output("status", "--porcelain"), "steps": []}
    save_json(output / "manifest.json", manifest)

    def finish(status, reason):
        manifest.update(status=status, reason=reason, finished_utc=datetime.now(timezone.utc).isoformat())
        save_json(output / "manifest.json", manifest)
        print(f"{status.upper()}: {reason}\nEvidence: {output}")
        return 0 if status == "passed" else 2 if status == "blocked" else 1

    def step(name, command, cwd, timeout=120, env=None):
        result = run_step(name, command, cwd, output, timeout, env)
        manifest["steps"].append(result)
        save_json(output / "manifest.json", manifest)
        print(f"{result['status'].upper()}: {name}", flush=True)
        return result["status"] == "passed"

    if platform.system() != "Linux":
        return finish("blocked", "Linux is required; no module was built or loaded")
    if args.integration and os.geteuid() != 0:
        return finish("blocked", "integration requires root inside a disposable Linux guest")
    tools = ["git", "make", "gcc", "bash", "modinfo", "timeout", "python3"]
    if args.integration:
        tools += ["dmesg", "insmod", "rmmod", "lsmod"]
    missing = [tool for tool in tools if shutil.which(tool) is None]
    if missing:
        return finish("blocked", "missing tools: " + ", ".join(missing))
    release = platform.release()
    headers = Path("/lib/modules") / release / "build"
    manifest["kernel_release"] = release
    manifest["kernel_headers"] = str(headers.resolve())
    if not (headers / "Makefile").is_file():
        return finish("blocked", f"matching build headers missing: {headers}")
    if args.integration and Path("/sys/module/ringbuf_char").exists():
        return finish("blocked", "ringbuf_char is already loaded; use a clean disposable guest")
    if args.integration and not step("dmesg-before", ["dmesg", "--color=never"], ROOT):
        return finish("blocked", "kernel diagnostics are unreadable")
    try:
        tracked = subprocess.check_output(["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
                                          cwd=ROOT, timeout=10).decode().split("\0")
        # Output must not be recursively captured if placed outside ignored artifacts/.
        files = [name for name in tracked if name and not (ROOT / name).resolve().is_relative_to(output)]
        with tempfile.TemporaryDirectory(prefix="kernelbridge-", dir="/tmp") as temporary:
            build = Path(temporary)
            manifest["source_files"] = snapshot(ROOT, build, files)
            with tarfile.open(output / "build-source.tar.gz", "w:gz") as archive:
                for name in manifest["source_files"]:
                    archive.add(build / name, arcname=name, recursive=False)
            for config in [Path("/proc/config.gz"), Path("/boot") / f"config-{release}", headers / ".config"]:
                if config.is_file():
                    data = gzip.decompress(config.read_bytes()) if config.suffix == ".gz" else config.read_bytes()
                    (output / "kernel.config").write_bytes(data)
                    manifest["kernel_config_source"] = str(config)
                    break
            else:
                manifest["kernel_config_source"] = None
            save_json(output / "manifest.json", manifest)
            for name, command in [
                ("compiler", ["gcc", "--version"]),
                ("userspace-build", ["make", "userspace"]),
                ("startup-test", ["make", "-C", "userspace", "test"]),
                ("shell-check", ["bash", "scripts/check_shell.sh"]),
                ("kernel-build", ["make", "module", f"KDIR={headers}", "W=1"]),
                ("module-vermagic", ["modinfo", "-F", "vermagic", str(build / "ringbuf_char.ko")])]:
                if not step(name, command, build, timeout=300):
                    return finish("failed", f"required step failed: {name}")
            vermagic = (output / "module-vermagic.log").read_text().split()
            if not vermagic or vermagic[0] != release:
                return finish("failed", "module vermagic does not match running kernel")
            shutil.copy2(build / "ringbuf_char.ko", output / "ringbuf_char.ko")
            manifest["module_sha256"] = hashlib.sha256((output / "ringbuf_char.ko").read_bytes()).hexdigest()
            if not args.integration:
                return finish("passed", "build checks passed; runtime was not requested")
            env = dict(os.environ, LOG_DIR=str(output / "integration"),
                       CONTRACT_OUTPUT=str(output / "contract"), W="1")
            integration_ok = False
            try:
                integration_ok = step("integration-suite", ["bash", "tests/run_all_tests.sh"], build, 600, env)
            finally:
                cleanup_ok = step("module-cleanup", ["bash", "scripts/unload.sh", "--quiet"], build, 20)
                diagnostics_ok = step("dmesg-after", ["dmesg", "--color=never"], build, 20)
            if not cleanup_ok or Path("/sys/module/ringbuf_char").exists():
                return finish("failed", "module cleanup failed; inspect guest before reuse")
            if not diagnostics_ok:
                return finish("failed", "final kernel diagnostics unavailable")
            manifest["post_test_module_sha256"] = hashlib.sha256((build / "ringbuf_char.ko").read_bytes()).hexdigest()
            if manifest["post_test_module_sha256"] != manifest["module_sha256"]:
                return finish("failed", "module binary changed during testing; identity is ambiguous")
            diagnostic = new_kernel_messages((output / "dmesg-before.log").read_text(errors="replace"),
                                             (output / "dmesg-after.log").read_text(errors="replace"))
            save_json(output / "kernel-diagnostics.json", diagnostic)
            if not integration_ok or diagnostic["status"] != "passed":
                return finish("failed", "integration or kernel diagnostic checks did not pass")
            manifest["runtime_validated"] = True
            return finish("passed", "integration suite passed for this module and kernel")
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        return finish("failed", f"{type(exc).__name__}: {exc}")


if __name__ == "__main__":
    raise SystemExit(main())
