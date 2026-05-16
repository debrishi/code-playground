# Deployment — code-lambda

Live in **`ap-south-1`** (Mumbai), account `694318441020`, arm64, container image.

| Resource | Value |
|---|---|
| ECR image | `694318441020.dkr.ecr.ap-south-1.amazonaws.com/code-lambda:latest` |
| Lambda ARN | `arn:aws:lambda:ap-south-1:694318441020:function:code-lambda` |
| Architecture | `arm64` |
| Memory / Timeout | `1024 MB` / `20 s` |
| Reserved concurrency | `10` |
| Function URL | `https://kvdcixmh7iojuulgcyg7p7tiia0rwhps.lambda-url.ap-south-1.on.aws/` |
| Auth | `NONE` + CORS `*` for POST |

## Steps

### 1. Build image for Lambda

Lambda rejects OCI multi-platform manifests — build a single-arch Docker v2 manifest.

```bash
docker buildx build --platform linux/arm64 --provenance=false --output=type=docker \
  -t code-lambda .
```

### 2. Push to ECR

```bash
aws ecr create-repository --region ap-south-1 --repository-name code-lambda \
  --image-scanning-configuration scanOnPush=true

aws ecr get-login-password --region ap-south-1 \
  | docker login --username AWS --password-stdin 694318441020.dkr.ecr.ap-south-1.amazonaws.com

docker tag code-lambda:latest 694318441020.dkr.ecr.ap-south-1.amazonaws.com/code-lambda:latest
docker push 694318441020.dkr.ecr.ap-south-1.amazonaws.com/code-lambda:latest
```

### 3. Execution role

```bash
aws iam create-role --region ap-south-1 --role-name code-lambda-exec-role \
  --assume-role-policy-document '{"Version":"2012-10-17","Statement":[{"Effect":"Allow","Principal":{"Service":"lambda.amazonaws.com"},"Action":"sts:AssumeRole"}]}'

aws iam attach-role-policy --region ap-south-1 --role-name code-lambda-exec-role \
  --policy-arn arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole

sleep 10   # IAM propagation
```

### 4. Create Lambda

```bash
aws lambda create-function --region ap-south-1 \
  --function-name code-lambda \
  --package-type Image \
  --code ImageUri=694318441020.dkr.ecr.ap-south-1.amazonaws.com/code-lambda:latest \
  --role arn:aws:iam::694318441020:role/code-lambda-exec-role \
  --architectures arm64 \
  --memory-size 1024 \
  --timeout 20
```

Wait until `State=Active`:
```bash
aws lambda get-function --region ap-south-1 --function-name code-lambda \
  --query 'Configuration.State' --output text
```

### 5. Function URL + public invoke permissions

Since Oct 2025, Lambda requires **both** `InvokeFunctionUrl` **and** `InvokeFunction` permissions.

```bash
aws lambda create-function-url-config --region ap-south-1 --function-name code-lambda \
  --auth-type NONE \
  --cors '{"AllowOrigins":["*"],"AllowMethods":["POST"],"AllowHeaders":["content-type"],"MaxAge":86400}'

aws lambda add-permission --region ap-south-1 --function-name code-lambda \
  --statement-id FunctionUrlAllowPublicAccess \
  --action lambda:InvokeFunctionUrl \
  --principal '*' \
  --function-url-auth-type NONE

aws lambda add-permission --region ap-south-1 --function-name code-lambda \
  --statement-id FunctionUrlAllowPublicInvoke \
  --action lambda:InvokeFunction \
  --principal '*'
# Newer CLIs support `--invoked-via-function-url` to scope this to URL traffic only.
```

### 6. Concurrency cap

```bash
aws lambda put-function-concurrency --region ap-south-1 --function-name code-lambda \
  --reserved-concurrent-executions 10
```

### 7. Smoke test

```bash
URL=https://kvdcixmh7iojuulgcyg7p7tiia0rwhps.lambda-url.ap-south-1.on.aws/
curl -s -X POST -H 'Content-Type: application/json' $URL -d '{"is_warmup":true}'
curl -s -X POST -H 'Content-Type: application/json' $URL \
  -d '{"language":"python","code":"print(1+1)"}'
```

## Redeploy after code changes

```bash
docker buildx build --platform linux/arm64 --provenance=false --output=type=docker -t code-lambda .
docker tag code-lambda:latest 694318441020.dkr.ecr.ap-south-1.amazonaws.com/code-lambda:latest
docker push 694318441020.dkr.ecr.ap-south-1.amazonaws.com/code-lambda:latest
aws lambda update-function-code --region ap-south-1 --function-name code-lambda \
  --image-uri 694318441020.dkr.ecr.ap-south-1.amazonaws.com/code-lambda:latest
```

## Issues we hit

1. **Initial ECR push used OCI image-index manifest.**
   Docker Desktop's default `buildx` pushed `application/vnd.oci.image.index.v1+json`, which Lambda rejects with
   `InvalidParameterValueException: The image manifest ... is not supported.`
   **Fix:** `docker buildx build --platform linux/arm64 --provenance=false --output=type=docker` forces a single-arch v2 manifest.

2. **Function URLs are not supported in `ap-south-2` (Hyderabad).**
   Every `*-function-url-config` call returned `AccessDeniedException: Unable to determine service/operation name to be authorized`. Not a perms issue — the API just isn't available in several newer regions (`ap-south-2`, `ap-southeast-4`, `eu-south-2`, `eu-central-2`, `il-central-1`, `me-central-1`).
   **Fix:** redeployed to `ap-south-1`.

3. **`NONE` auth type returned 403 Forbidden after adding only `InvokeFunctionUrl`.**
   Since October 2025, AWS requires **both** `lambda:InvokeFunctionUrl` **and** `lambda:InvokeFunction` permissions on the resource-based policy.
   **Fix:** added a second `add-permission` statement for `lambda:InvokeFunction`.

4. **Java cold start tripped `COMPILE_TIME_LIMIT_EXCEEDED` at 512 MB memory.**
   `javac` startup took >10s cold because Lambda CPU scales with memory, and at 512 MB there wasn't enough vCPU.
   **Fix:** bumped function memory to 1024 MB. Warm invocations were fine even at 512 MB; cold starts now comfortably fit in the 10s compile budget.

## Not yet wired up

- **VPC with no NAT gateway** — README's network-sandbox layer. For now the only network block is the 10s subprocess timeout.
- **EventBridge warmer** — keeps a container hot with a `{"is_warmup": true}` ping every 5 min.
- **CloudWatch Logs VPC endpoint** — needed only once the function moves into a VPC.
