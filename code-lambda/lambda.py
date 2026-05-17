"""AWS Lambda handler that runs user code in C++, Java, Python, or TypeScript.

Sandboxing:
  * 10s subprocess timeout, killed as a process group (no orphan survivors).
  * 256MB address-space cap for languages that don't self-manage heap.
  * 50 forks per invocation, 10MB max file size, 4KB stdout/stderr cap.
  * Per-invocation temp dir, wiped in `finally`.
"""
import json
import os
import re
import resource
import shutil
import signal
import subprocess
import tempfile
import time

# --- Limits (per README MVP) ---
MAX_TIME_SEC = 10                   # user-code wall-clock
MAX_MEMORY_MB = 256                 # RLIMIT_AS cap, JVM -Xmx, Node --max-old-space-size
MAX_FILE_SIZE_MB = 10               # RLIMIT_FSIZE — stops /tmp fill attacks
MAX_NPROC = 50                      # RLIMIT_NPROC
MAX_OUTPUT_SIZE = 4096              # bytes of stdout/stderr returned to the caller
TRUNCATED_MSG = f"\n[OUTPUT_TRUNCATED: Exceeded {MAX_OUTPUT_SIZE}B Limit]"

# Substrings we look for in stderr to surface a clean MEMORY_LIMIT_EXCEEDED.
OOM_SIGNATURES = (
    "MemoryError",                      # Python
    "OutOfMemoryError",                 # JVM
    "JavaScript heap out of memory",    # Node
    "std::bad_alloc",                   # C++
    "AddressSanitizer: out of memory",  # C++ under ASan
)

# Language runtime definitions.
#   cap_memory=True applies RLIMIT_AS to the subprocess. JVM, Node, and ASan-
#   instrumented C++ manage/reserve their own address space and crash if
#   RLIMIT_AS is set too low.
#   Java is resolved per-invocation from `public class <Name>` in the source.
LANG_CONFIG = {
    "python": {
        "source": "main.py",
        "compile": None,
        "run": ["python3", "main.py"],
        "cap_memory": True,
    },
    "cpp": {
        "source": "main.cpp",
        # -O2 + C++17; ASan catches OOB and use-after-free at runtime.
        "compile": ["g++", "-std=c++17", "-O2",
                    "-fsanitize=address", "-fno-omit-frame-pointer",
                    "-g", "-o", "main", "main.cpp"],
        "run": ["./main"],
        # ASan reserves ~8GB virtual space for shadow memory, so RLIMIT_AS is
        # off. Container memory cap is the backstop; ASan itself reports OOM.
        "cap_memory": False,
        "env": {"ASAN_OPTIONS": "abort_on_error=1:halt_on_error=1:detect_leaks=0"},
    },
    "typescript": {
        "source": "main.ts",
        "compile": None,
        "run": ["node", f"--max-old-space-size={MAX_MEMORY_MB}",
                "--experimental-strip-types", "main.ts"],
        "cap_memory": False,
    },
    "java": {},  # resolved by _resolve_java(code)
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


def _preexec(cap_memory, cap_file_size=True):
    """Return a preexec_fn that applies RLIMITs and detaches the subprocess
    into a new session so the whole tree can be killed on timeout.
    """
    def _try(fn):
        try:
            fn()
        except (ValueError, OSError):
            pass

    def apply_limits():
        if cap_memory:
            mem = MAX_MEMORY_MB * 1024 * 1024
            _try(lambda: resource.setrlimit(resource.RLIMIT_AS, (mem, mem)))
        _try(lambda: resource.setrlimit(resource.RLIMIT_NPROC, (MAX_NPROC, MAX_NPROC)))
        if cap_file_size:
            fsize = MAX_FILE_SIZE_MB * 1024 * 1024
            _try(lambda: resource.setrlimit(resource.RLIMIT_FSIZE, (fsize, fsize)))
        _try(os.setsid)
    return apply_limits


def _run(cmd, workdir, stdin_data, cap_memory, env_extra=None, cap_file_size=True):
    """Run a subprocess in its own process group.
    Returns (returncode, stdout, stderr, timed_out).
    """
    out_path = os.path.join(workdir, "stdout")
    err_path = os.path.join(workdir, "stderr")
    env = {**os.environ, **env_extra} if env_extra else None
    with open(out_path, "w") as out, open(err_path, "w") as err:
        p = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE if stdin_data is not None else subprocess.DEVNULL,
            stdout=out, stderr=err,
            preexec_fn=_preexec(cap_memory, cap_file_size),
            text=True, cwd=workdir, env=env,
        )
        try:
            p.communicate(input=stdin_data, timeout=MAX_TIME_SEC)
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


def _resolve_java(code):
    """Build Java cfg by extracting `public class <Name>` from the source.
    Returns (cfg, None) on success, or (None, error_response) on missing class.
    """
    m = re.search(r"public\s+class\s+(\w+)\b", code)
    if not m:
        return None, _response(400, {
            "error": "COMPILATION_ERROR",
            "details": 'Java code must define a `public class` containing `public static void main(String[] args)`.',
        })
    name = m.group(1)
    return {
        "source": f"{name}.java",
        "compile": ["javac", f"{name}.java"],
        "run": ["java", f"-Xmx{MAX_MEMORY_MB}m", name],
        "cap_memory": False,
    }, None


def lambda_handler(event, context):
    # Function URL wraps the body as a string; direct invokes pass a dict.
    if isinstance(event, dict) and isinstance(event.get("body"), str):
        try:
            event = json.loads(event["body"])
        except json.JSONDecodeError:
            return _response(400, {"error": "Invalid JSON"})

    # EventBridge warmup ping.
    if event.get("is_warmup"):
        return _response(200, {"warm": True})

    code = event.get("code")
    lang = event.get("language", "python")
    stdin_data = event.get("stdin", "")

    if not code:
        return _response(400, {"error": "No code provided"})
    if lang not in LANG_CONFIG:
        return _response(400, {"error": f"Unsupported language: {lang}"})

    if lang == "java":
        cfg, err = _resolve_java(code)
        if err:
            return err
    else:
        cfg = LANG_CONFIG[lang]

    workdir = None
    try:
        workdir = tempfile.mkdtemp(prefix="run_")
        with open(os.path.join(workdir, cfg["source"]), "w") as f:
            f.write(code)

        # Compile step runs uncapped — compilers can legitimately need more
        # memory and produce binaries larger than the user-code FSIZE cap.
        compile_ms = None
        if cfg["compile"]:
            t0 = time.perf_counter()
            rc, _, cerr, to = _run(cfg["compile"], workdir, None,
                                   cap_memory=False, cap_file_size=False)
            compile_ms = round((time.perf_counter() - t0) * 1000)
            if to:
                return _response(400, {"error": "COMPILE_TIME_LIMIT_EXCEEDED"})
            if rc != 0:
                return _response(400, {"error": "COMPILATION_ERROR", "details": cerr})

        # `run_ms` is the wall-clock around the subprocess: fork + exec + the
        # user's program + Python-side communicate() bookkeeping. Tiny
        # programs floor out at ~10ms (~5ms locally) because of fork/exec
        # overhead, not because the timer is broken. C++/Java toy programs
        # also benefit from g++ -O2 dead-code elimination, so a 1e8-iter
        # loop summing into a non-volatile variable runs in <1ms — the
        # compiler folded it. Use `volatile` to force real execution when
        # benchmarking.
        t0 = time.perf_counter()
        rc, output, error, to = _run(cfg["run"], workdir, stdin_data,
                                     cap_memory=cfg["cap_memory"],
                                     env_extra=cfg.get("env"))
        run_ms = round((time.perf_counter() - t0) * 1000)
        if to:
            return _response(400, {"error": "TIME_LIMIT_EXCEEDED"})
        if rc != 0:
            if any(sig in error for sig in OOM_SIGNATURES):
                return _response(400, {"error": "MEMORY_LIMIT_EXCEEDED"})
            return _response(400, {
                "error": "RUNTIME_ERROR", "output": output, "details": error,
                "compile_ms": compile_ms, "run_ms": run_ms,
            })
        return _response(200, {
            "output": output,
            "compile_ms": compile_ms,
            "run_ms": run_ms,
        })

    except Exception as e:
        return _response(500, {"error": str(e)})
    finally:
        if workdir:
            shutil.rmtree(workdir, ignore_errors=True)
