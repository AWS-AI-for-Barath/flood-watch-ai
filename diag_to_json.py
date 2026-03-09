"""Write diagnostics to JSON file for easy reading."""
import boto3, json

lam = boto3.client("lambda")
s3 = boto3.client("s3")
results = {}

# processFloodAI
func = lam.get_function(FunctionName="processFloodAI")
c = func["Configuration"]
results["processFloodAI"] = {
    "runtime": c["Runtime"], "handler": c["Handler"],
    "timeout": c["Timeout"], "memory": c["MemorySize"], "state": c["State"],
    "env": c.get("Environment", {}).get("Variables", {})
}

# S3 notifications
notif = s3.get_bucket_notification_configuration(Bucket="floodwatch-uploads")
results["s3_notifications"] = {
    k: v for k, v in notif.items() if k != "ResponseMetadata"
}

# Direct invoke test
payload = {"Records": [{"s3": {"bucket": {"name": "floodwatch-uploads"}, "object": {"key": "media/e2e-test-diag.jpg"}}}]}
resp = lam.invoke(FunctionName="processFloodAI", InvocationType="RequestResponse", Payload=json.dumps(payload).encode())
results["invoke_processFloodAI"] = {
    "status": resp["StatusCode"],
    "error": resp.get("FunctionError"),
    "body": resp["Payload"].read().decode()[:1000]
}

# transformFloodPolygon
func2 = lam.get_function(FunctionName="transformFloodPolygon")
c2 = func2["Configuration"]
results["transformFloodPolygon"] = {
    "runtime": c2["Runtime"], "handler": c2["Handler"],
    "timeout": c2["Timeout"], "memory": c2["MemorySize"], "state": c2["State"],
    "env": c2.get("Environment", {}).get("Variables", {})
}

# routingLambda check
try:
    func3 = lam.get_function(FunctionName="routingLambda")
    c3 = func3["Configuration"]
    results["routingLambda"] = {
        "runtime": c3["Runtime"], "handler": c3["Handler"],
        "timeout": c3["Timeout"], "state": c3["State"],
        "env": c3.get("Environment", {}).get("Variables", {})
    }
except: pass

# processFloodAlerts  
try:
    func4 = lam.get_function(FunctionName="processFloodAlerts")
    c4 = func4["Configuration"]
    results["processFloodAlerts"] = {
        "runtime": c4["Runtime"], "handler": c4["Handler"],
        "timeout": c4["Timeout"], "state": c4["State"],
        "env": c4.get("Environment", {}).get("Variables", {})
    }
except: pass

# simulateFloodPropagation
try:
    func5 = lam.get_function(FunctionName="simulateFloodPropagation")
    c5 = func5["Configuration"]
    results["simulateFloodPropagation"] = {
        "runtime": c5["Runtime"], "handler": c5["Handler"],
        "timeout": c5["Timeout"], "state": c5["State"],
        "env": c5.get("Environment", {}).get("Variables", {})
    }
except: pass

with open("diag.json", "w") as f:
    json.dump(results, f, indent=2, default=str)
print("DONE - wrote diag.json")
