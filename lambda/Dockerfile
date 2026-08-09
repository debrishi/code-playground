FROM public.ecr.aws/lambda/python:3.14

# Toolchains for the three supported languages:
#   clang              -> C++ with AddressSanitizer. clang ships its own ASan
#                         runtime and pulls in libstdc++-devel (the standard
#                         library headers, incl. <bits/stdc++.h>) as a dependency,
#                         so no separate GCC package is needed.
#   Corretto 25        -> Java (javac + java)
# Python user code runs on the base image's own python 3.14.
#
# Slimming: no weak deps, no docs/man pages — keeps the image small so cold
# starts pull less data.  compiler-rt (ASan static runtime) is normally a weak
# dep of clang, so with weak deps off it must be listed explicitly.
# No `dnf update`: rebuild on a fresh base instead
# (keeps layers lean and builds reproducible).
RUN dnf install -y --setopt=install_weak_deps=0 --setopt=tsflags=nodocs \
        clang compiler-rt java-25-amazon-corretto-devel && \
    dnf clean all && \
    rm -rf /var/cache/dnf /usr/share/man /usr/share/doc && \
    # Trim toolchain fat never executed at runtime (~200MB uncompressed).
    # Deletions must live in this same RUN, or the layer diff keeps the bytes.
    #   - GCC's internal compilers: clang has its own frontend; the gcc
    #     package stays only for its link-time pieces (crt*.o, libgcc).
    rm -f /usr/libexec/gcc/aarch64-amazon-linux/11/cc1 \
          /usr/libexec/gcc/aarch64-amazon-linux/11/cc1plus \
          /usr/libexec/gcc/aarch64-amazon-linux/11/lto1 && \
    #   - Standalone LLVM tools, except the symbolizer ASan uses for
    #     readable stack traces.
    find /usr/bin -maxdepth 1 -name 'llvm-*' ! -name 'llvm-symbolizer' -delete && \
    #   - libclang C API: used by IDE tooling, not by the clang++ driver.
    rm -f /usr/lib64/libclang.so.15.0.7 /usr/lib64/libclang.so.15 && \
    #   - JDK source archive.
    rm -f /usr/lib/jvm/java-25-amazon-corretto.aarch64/lib/src.zip && \
    #   - RPMs pulled in as dependencies but unused at runtime: make/guile
    #     (build tools), python3.9 (runtime uses /var/lang python3.14),
    #     gconv-extra (exotic charsets; base glibc keeps the common ones).
    rpm -e --nodeps make guile22 python3 python3-libs \
        python3-pip-wheel python3-setuptools-wheel glibc-gconv-extra && \
    #   - Default CDS archives: every java run here uses our AOT cache
    #     (built below) instead; the JVM falls back gracefully regardless.
    rm -f /usr/lib/jvm/java-25-amazon-corretto.aarch64/lib/server/*.jsa && \
    #   - ct.sym is only needed for `javac --release N` cross-compilation.
    rm -f /usr/lib/jvm/java-25-amazon-corretto.aarch64/lib/ct.sym && \
    #   - gettext message catalogs — English-only tool output is fine.
    rm -rf /usr/share/locale

# ---------- Python: sortedcontainers (LeetCode parity) -----------------------
# Pure-Python, ~100KB — SortedList/SortedDict/SortedSet for Map/TreeMap-style
# problems, mirroring LeetCode's Python3 environment.
RUN pip install --no-cache-dir sortedcontainers

# ---------- C++ Precompiled Header (PCH) ------------------------------------
# `#include <bits/stdc++.h>` pulls in the entire C++ standard library — thousands
# of lines of template-heavy headers that take ~1-2s to parse on every compile.
#
# Pre-compiling this header during `docker build` serialises the parsed AST into
# a .pch file.  At runtime, clang loads the pre-parsed AST instead of re-parsing
# from scratch.
#
# The PCH MUST be built with the exact same flags used at compile time; a flag
# mismatch causes clang to silently ignore the PCH or error out.
# -std=c++2b is C++23 on AL2023's clang 15 (the c++23 spelling landed in
# clang 17) — mirrors LeetCode's C++ environment (clang, C++23, -O2, ASan).
RUN mkdir -p /opt/cpp-pch && \
    echo '#include <bits/stdc++.h>' > /opt/cpp-pch/stdc++.h && \
    clang++ -std=c++2b -O2 -fno-finite-loops -fsanitize=address \
            -fno-omit-frame-pointer -g \
            -x c++-header /opt/cpp-pch/stdc++.h \
            -o /opt/cpp-pch/stdc++.h.pch

# ---------- Java AOT Cache (JEP 514 / 515 — Corretto 25) -------------------
# Source-launch mode (`java Main.java`) loads the internal javac compiler on
# every invocation — ~200 classes that take 1-2s to parse + verify + link.
#
# A training run during `docker build` captures all of those classes (plus the
# JDK core) into an AOT cache. At runtime the JVM memory-maps the pre-linked
# metadata and, with JEP 515, also loads pre-recorded method profiles so C1
# can emit optimized code immediately instead of starting from the interpreter.
#
# Net effect: Java source-launch cold-start drops from ~3-4s to ~1-1.5s.
RUN mkdir -p /opt/java-aot && \
    echo 'class Warmup { public static void main(String[] args) { System.out.println("ok"); } }' \
        > /tmp/Warmup.java && \
    java -XX:AOTCacheOutput=/opt/java-aot/source-launch.aot \
         -XX:TieredStopAtLevel=1 -XX:+UseSerialGC \
         /tmp/Warmup.java && \
    rm /tmp/Warmup.java

COPY lambda.py ${LAMBDA_TASK_ROOT}/app.py

CMD ["app.lambda_handler"]
