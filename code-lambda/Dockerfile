FROM public.ecr.aws/lambda/python:3.12

# Toolchains for the four supported languages:
#   gcc-c++ + libasan  -> C++ with AddressSanitizer
#   Corretto 17        -> Java (javac + java)
#   Node.js 22         -> TypeScript via `node --experimental-strip-types`
# The python:3.12 base is Amazon Linux 2023 (glibc 2.34), which Node 22 needs.
RUN dnf update -y && \
    dnf install -y gcc-c++ libasan java-17-amazon-corretto-devel && \
    curl -fsSL https://rpm.nodesource.com/setup_22.x | bash - && \
    dnf install -y nodejs && \
    dnf clean all && rm -rf /var/cache/dnf

COPY lambda.py ${LAMBDA_TASK_ROOT}/app.py

CMD ["app.lambda_handler"]
