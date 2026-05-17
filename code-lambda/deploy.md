# Deployment — code-lambda

Containerised Python Lambda exposed via a public Function URL. Run from `code-lambda/`.

Prereqs: `aws login` complete, `docker buildx`, region set (`ap-south-1` here).

```bash
export AWS_REGION=ap-south-1
export AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
export ECR=$AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com/code-lambda
```

## 1. Build

```bash
docker buildx build --platform linux/arm64 --provenance=false --output=type=docker \
  -t code-lambda .
```

Both `--provenance=false` and `--output=type=docker` are needed: BuildKit otherwise wraps the image in an OCI index that Lambda's container loader rejects.

## 2. Test locally

```bash
docker run --rm -d -p 9000:8080 --name code-lambda-test code-lambda
./test_suite.sh                       # core: warmup, all 4 langs, limits, errors
./test_stdin.sh                       # stdin handling per language
./test_stress.sh                      # body-wrap, isolation, unicode, large stdin
docker stop code-lambda-test
```

All three scripts hit the local Lambda Runtime Interface Emulator on `:9000`. Don't push if any fail.

## 3. Push to ECR

```bash
aws ecr create-repository --region $AWS_REGION --repository-name code-lambda \
  --image-scanning-configuration scanOnPush=true

aws ecr get-login-password --region $AWS_REGION \
  | docker login --username AWS --password-stdin $ECR

docker tag code-lambda:latest $ECR:latest
docker push $ECR:latest
```

## 4. Execution role

```bash
aws iam create-role --role-name code-lambda-exec-role \
  --assume-role-policy-document '{"Version":"2012-10-17","Statement":[{"Effect":"Allow","Principal":{"Service":"lambda.amazonaws.com"},"Action":"sts:AssumeRole"}]}'

aws iam attach-role-policy --role-name code-lambda-exec-role \
  --policy-arn arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole

sleep 10   # IAM propagation
```

## 5. Create function

```bash
aws lambda create-function --region $AWS_REGION \
  --function-name code-lambda \
  --package-type Image \
  --code ImageUri=$ECR:latest \
  --role arn:aws:iam::$AWS_ACCOUNT_ID:role/code-lambda-exec-role \
  --architectures arm64 \
  --memory-size 1024 \
  --timeout 20

# Wait for State=Active
aws lambda get-function --region $AWS_REGION --function-name code-lambda \
  --query 'Configuration.State' --output text
```

## 6. Function URL

Lambda requires **both** `InvokeFunctionUrl` and `InvokeFunction` (since Oct 2025).

```bash
aws lambda create-function-url-config --region $AWS_REGION --function-name code-lambda \
  --auth-type NONE \
  --cors '{"AllowOrigins":["*"],"AllowMethods":["POST"],"AllowHeaders":["content-type"],"MaxAge":86400}'

aws lambda add-permission --region $AWS_REGION --function-name code-lambda \
  --statement-id FunctionUrlAllowPublicAccess \
  --action lambda:InvokeFunctionUrl --principal '*' --function-url-auth-type NONE

aws lambda add-permission --region $AWS_REGION --function-name code-lambda \
  --statement-id FunctionUrlAllowPublicInvoke \
  --action lambda:InvokeFunction --principal '*'

export FUNCTION_URL=$(aws lambda get-function-url-config --region $AWS_REGION \
  --function-name code-lambda --query FunctionUrl --output text)
echo $FUNCTION_URL
```

Save `$FUNCTION_URL` for the frontend's `VITE_LAMBDA_URL`.

## 7. Concurrency cap

```bash
aws lambda put-function-concurrency --region $AWS_REGION --function-name code-lambda \
  --reserved-concurrent-executions 10
```

## 8. Smoke test

```bash
curl -s -X POST -H 'Content-Type: application/json' $FUNCTION_URL -d '{"is_warmup":true}'
curl -s -X POST -H 'Content-Type: application/json' $FUNCTION_URL \
  -d '{"language":"python","code":"print(1+1)"}'
```

## Redeploy

```bash
docker buildx build --platform linux/arm64 --provenance=false --output=type=docker -t code-lambda .
./test_suite.sh && ./test_stdin.sh && ./test_stress.sh   # optional, recommended
docker tag code-lambda:latest $ECR:latest
docker push $ECR:latest
aws lambda update-function-code --region $AWS_REGION --function-name code-lambda \
  --image-uri $ECR:latest
```

## Notes

- **Region.** Function URLs aren't supported in `ap-south-2`, `ap-southeast-4`, `eu-south-2`, `eu-central-2`, `il-central-1`, `me-central-1`. Use `ap-south-1` or another mainstream region.
- **Memory.** Don't drop below 1024 MB — `javac` cold start needs the CPU that scales with memory or it trips `COMPILE_TIME_LIMIT_EXCEEDED`.
