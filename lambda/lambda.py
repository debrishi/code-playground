"""AWS Lambda handler that runs user code in C++, Java, or Python.

Sandboxing: 10s group-killed subprocess timeout, 512MB per-language memory
cap, 50 forks, 10MB max file size, 4KB output cap, per-invocation temp dir.
"""
import json
import logging
import os
import resource
import shutil
import signal
import subprocess
import tempfile
import time

logger = logging.getLogger()

MAX_TIME_SEC = 10                   # combined compile + run budget
MAX_MEMORY_MB = 512                 # per-language cap: ulimit -v / -Xmx / ASan rss
MAX_FILE_SIZE_MB = 10               # RLIMIT_FSIZE — stops /tmp fill attacks
MAX_NPROC = 50                      # RLIMIT_NPROC
MAX_OUTPUT_SIZE = 4096              # bytes of stdout/stderr returned to the caller
MAX_CODE_BYTES = 128 * 1024         # source size cap — rejects giant payloads early
MAX_STDIN_BYTES = 128 * 1024        # stdin size cap
TRUNCATED_MSG = f"\n[OUTPUT_TRUNCATED: Exceeded {MAX_OUTPUT_SIZE}B Limit]"

# Built during `docker build` (see Dockerfile): pre-parsed <bits/stdc++.h>
# AST, and a JVM AOT cache of the source-launch/javac classes.
CPP_PCH = "/opt/cpp-pch/stdc++.h.pch"
JAVA_AOT_CACHE = "/opt/java-aot/source-launch.aot"

# stderr substrings that map a non-zero exit to ERROR_MLE.
OOM_SIGNATURES = (
    "MemoryError",                      # Python
    "OutOfMemoryError",                 # JVM
    "std::bad_alloc",                   # C++
    "AddressSanitizer: out of memory",  # C++ under ASan
    "rss limit exhausted",              # C++ ASan hard_rss_limit_mb
)


def _warm_toolchains():
    """INIT-phase warming: use the burst CPU to page in the toolchains so the
    first user invocation skips the cold page-fault IO."""
    # Read PCH + AOT cache end-to-end; the runs below only touch parts.
    for path in (CPP_PCH, JAVA_AOT_CACHE):
        try:
            with open(path, "rb") as f:
                while f.read(1 << 20):
                    pass
        except OSError:
            pass
    try:
        subprocess.run(
            ["clang++", "-std=c++2b", "-O2", "-fno-finite-loops",
             "-fsanitize=address", "-fno-omit-frame-pointer", "-g",
             "-include-pch", CPP_PCH,
             "-x", "c++", "-", "-fsyntax-only"],
            input="int main(){}", text=True,
            timeout=MAX_TIME_SEC, capture_output=True,
        )
    except Exception:
        pass
    # Source-launch a real program (not `java -version`) so the in-memory
    # javac path is faulted in now.  Flags match LANG_CONFIG.
    warm_dir = None
    try:
        warm_dir = tempfile.mkdtemp(prefix="warm_")
        with open(os.path.join(warm_dir, "W.java"), "w") as f:
            f.write('class W { public static void main(String[] a) {'
                    ' System.out.print("ok"); } }')
        subprocess.run(
            ["java", f"-XX:AOTCache={JAVA_AOT_CACHE}",
             "-XX:TieredStopAtLevel=1", "-XX:+UseSerialGC",
             "W.java"],
            cwd=warm_dir, timeout=MAX_TIME_SEC, capture_output=True,
        )
    except Exception:
        pass
    finally:
        if warm_dir:
            shutil.rmtree(warm_dir, ignore_errors=True)

_warm_toolchains()


# {source, run} per language: write code to `source`, run one subprocess
# (compile + run share it).  Each `run` self-caps memory; `exec` makes the
# timeout kill the real process, not the wrapper shell.
LANG_CONFIG = {
    "python": {
        "source": "main.py",
        "run": ["sh", "-c", f"ulimit -v {MAX_MEMORY_MB * 1024}; exec python3 main.py"],
    },
    "cpp": {
        # -fno-finite-loops keeps `while(1){}` alive under -O2.
        # ASan reserves ~8GB virtual, so memory is capped via its RSS limiter.
        "source": "main.cpp",
        "run": ["sh", "-c",
                "export ASAN_OPTIONS=abort_on_error=1:halt_on_error=1:"
                f"detect_leaks=0:hard_rss_limit_mb={MAX_MEMORY_MB}; "
                "clang++ -std=c++2b -O2 -fno-finite-loops -fsanitize=address "
                f"-fno-omit-frame-pointer -g -include-pch {CPP_PCH} "
                "-o main main.cpp && exec ./main"],
    },
    "java": {
        # Source-launch compiles in-memory; AOTCache + C1-only + SerialGC
        # shave ~2s off cold start for short-lived processes.
        "source": "Main.java",
        "run": ["java",
                f"-XX:AOTCache={JAVA_AOT_CACHE}",
                "-XX:TieredStopAtLevel=1",
                "-XX:+UseSerialGC",
                f"-Xmx{MAX_MEMORY_MB}m",
                "Main.java"],
    },
}


def _response(status_code, payload):
    return {
        "statusCode": status_code,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps(payload),
    }


def _read_capped(path):
    """Return up to MAX_OUTPUT_SIZE bytes; append truncation marker if larger."""
    try:
        size = os.path.getsize(path)
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            data = f.read(MAX_OUTPUT_SIZE)
        return data + TRUNCATED_MSG if size > MAX_OUTPUT_SIZE else data
    except OSError:
        return ""


def _preexec():
    """RLIMITs (nproc, fsize) + new session for group-kill."""
    def _try(fn):
        try:
            fn()
        except (ValueError, OSError):
            pass

    def apply_limits():
        _try(lambda: resource.setrlimit(resource.RLIMIT_NPROC, (MAX_NPROC, MAX_NPROC)))
        fsize = MAX_FILE_SIZE_MB * 1024 * 1024
        _try(lambda: resource.setrlimit(resource.RLIMIT_FSIZE, (fsize, fsize)))
        _try(os.setsid)
    return apply_limits


def _run(cmd, workdir, stdin_data, timeout=MAX_TIME_SEC):
    """Run cmd in its own process group -> (rc, stdout, stderr, timed_out)."""
    out_path = os.path.join(workdir, "stdout")
    err_path = os.path.join(workdir, "stderr")
    with open(out_path, "w") as out, open(err_path, "w") as err:
        p = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE if stdin_data is not None else subprocess.DEVNULL,
            stdout=out, stderr=err,
            preexec_fn=_preexec(),
            text=True, cwd=workdir,
        )
        try:
            p.communicate(input=stdin_data, timeout=timeout)
            return p.returncode, _read_capped(out_path), _read_capped(err_path), False
        except subprocess.TimeoutExpired:
            try:
                os.killpg(p.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            try:
                p.communicate(timeout=2)
            except subprocess.TimeoutExpired:
                pass
            return -1, _read_capped(out_path), _read_capped(err_path), True


def _validate(event):
    """Validate the request payload. Returns (config, code, stdin, error_response)."""
    if not isinstance(event, dict):
        return None, None, None, _response(400, {"error": "ERROR", "details": "Payload must be a JSON object"})

    code = event.get("code")
    lang = event.get("language", "python")
    stdin_data = event.get("stdin", "")

    if not code or not isinstance(code, str) or not code.strip():
        return None, None, None, _response(400, {"error": "ERROR", "details": "No code provided"})
    if len(code.encode("utf-8", errors="replace")) > MAX_CODE_BYTES:
        return None, None, None, _response(400, {"error": "ERROR", "details": f"Code exceeds {MAX_CODE_BYTES // 1024}KB limit"})
    if not isinstance(lang, str) or lang not in LANG_CONFIG:
        return None, None, None, _response(400, {"error": "ERROR", "details": f"Unsupported language: {lang}"})
    if not isinstance(stdin_data, str):
        return None, None, None, _response(400, {"error": "ERROR", "details": "stdin must be a string"})
    if len(stdin_data.encode("utf-8", errors="replace")) > MAX_STDIN_BYTES:
        return None, None, None, _response(400, {"error": "ERROR", "details": f"stdin exceeds {MAX_STDIN_BYTES // 1024}KB limit"})

    return LANG_CONFIG[lang], code, stdin_data, None


def lambda_handler(event, context):
    # Function URL wraps the body as a string; direct invokes pass a dict.
    if isinstance(event, dict) and isinstance(event.get("body"), str):
        try:
            event = json.loads(event["body"])
        except json.JSONDecodeError:
            return _response(400, {"error": "Invalid JSON"})

    # EventBridge warmer ping — respond immediately, run nothing.
    if isinstance(event, dict) and event.get("is_warmup"):
        return _response(200, {"warmed": True})

    cfg, code, stdin_data, err = _validate(event)
    if err:
        return err

    workdir = None
    try:
        workdir = tempfile.mkdtemp(prefix="run_")
        with open(os.path.join(workdir, cfg["source"]), "w") as f:
            f.write(code)

        t0 = time.perf_counter()
        rc, output, error, to = _run(cfg["run"], workdir, stdin_data,
                                     timeout=MAX_TIME_SEC)
        run_ms = round((time.perf_counter() - t0) * 1000)
        if to:
            return _response(400, {"error": "ERROR_TLE"})
        if rc != 0:
            # SIGKILL with no OOM signature = cgroup OOM-killer backstop.
            if rc == -signal.SIGKILL or any(sig in error for sig in OOM_SIGNATURES):
                return _response(400, {"error": "ERROR_MLE"})
            return _response(400, {
                "error": "ERROR", "output": output, "details": error,
                "run_ms": run_ms,
            })
        return _response(200, {
            "output": output,
            "run_ms": run_ms,
        })

    except Exception:
        # Log the full traceback to CloudWatch; never leak internals to the caller.
        logger.exception("Unhandled error while executing user code")
        return _response(500, {"error": "ERROR", "details": "Internal error"})
    finally:
        if workdir:
            shutil.rmtree(workdir, ignore_errors=True)
