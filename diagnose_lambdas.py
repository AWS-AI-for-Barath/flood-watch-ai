"""Diagnose Lambda issue - check config, invoke directly, examine errors."""
import boto3, json

lam = boto3.client("lambda")
s3 = boto3.client("s3")

# 1. Check processFloodAI config
print("=== processFloodAI CONFIG ===")
func = lam.get_function(FunctionName="processFloodAI")
config = func["Configuration"]
print(f"Runtime:  {config['Runtime']}")
print(f"Handler:  {config['Handler']}")
print(f"Timeout:  {config['Timeout']}s")
print(f"Memory:   {config['MemorySize']}MB")
print(f"State:    {config['State']}")
env = config.get("Environment", {}).get("Variables", {})
for k, v in sorted(env.items()):
    print(f"  ENV {k} = {v[:60]}")

# 2. Check S3 notification config on bucket
print("\n=== S3 NOTIFICATION CONFIG ===")
notif = s3.get_bucket_notification_configuration(Bucket="floodwatch-uploads")
for key in ["LambdaFunctionConfigurations", "EventBridgeConfiguration"]:
    val = notif.get(key)
    if val:
        print(f"{key}: {json.dumps(val, indent=2)[:500]}")

# 3. Direct invoke processFloodAI
print("\n=== DIRECT INVOKE processFloodAI ===")
payload = {
    "Records": [{
        "s3": {
            "bucket": {"name": "floodwatch-uploads"},
            "object": {"key": "media/e2e-test-diag.jpg"}
        }
    }]
}
# First upload a small test image
s3.put_object(
    Bucket="floodwatch-uploads",
    Key="media/e2e-test-diag.jpg",
    Body=b"\xff\xd8\xff\xe0" + b"test flood image data",
    ContentType="image/jpeg"
)
print("Uploaded test image")

resp = lam.invoke(
    FunctionName="processFloodAI",
    InvocationType="RequestResponse",
    Payload=json.dumps(payload).encode()
)
status = resp.get("StatusCode")
func_error = resp.get("FunctionError")
result_raw = resp["Payload"].read().decode()
print(f"Status: {status}")
print(f"FunctionError: {func_error}")
print(f"Response: {result_raw[:500]}")

# 4. Check transformFloodPolygon config
print("\n=== transformFloodPolygon CONFIG ===")
func2 = lam.get_function(FunctionName="transformFloodPolygon")
config2 = func2["Configuration"]
print(f"Runtime:  {config2['Runtime']}")
print(f"Handler:  {config2['Handler']}")
print(f"Timeout:  {config2['Timeout']}s")
env2 = config2.get("Environment", {}).get("Variables", {})
for k, v in sorted(env2.items()):
    print(f"  ENV {k} = {v[:60]}")
