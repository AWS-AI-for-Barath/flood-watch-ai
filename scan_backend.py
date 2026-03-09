"""FloodWatch AWS Backend Scanner - verify all deployed resources."""
import boto3, json

print("=" * 60)
print("  FLOODWATCH AWS BACKEND SCAN")
print("=" * 60)

# 1. Identity
sts = boto3.client('sts')
identity = sts.get_caller_identity()
print(f"\n[IDENTITY] Account: {identity['Account']}  User: {identity['Arn'].split('/')[-1]}")

# 2. Lambda Functions
lam = boto3.client('lambda')
funcs = lam.list_functions()['Functions']
print(f"\n[LAMBDAS] {len(funcs)} functions:")
for f in sorted(funcs, key=lambda x: x['FunctionName']):
    print(f"  - {f['FunctionName']:35s} {f.get('Runtime','N/A'):15s} {f.get('Handler','N/A')}")

# 3. S3 Bucket
s3 = boto3.client('s3')
try:
    objs = s3.list_objects_v2(Bucket='floodwatch-uploads', MaxKeys=50)
    contents = objs.get('Contents', [])
    prefixes = set()
    for o in contents:
        prefix = o['Key'].split('/')[0] + '/'
        prefixes.add(prefix)
    print(f"\n[S3] floodwatch-uploads: {len(contents)} objects")
    print(f"  Prefixes: {', '.join(sorted(prefixes))}")
    for o in contents[:10]:
        print(f"    {o['Key']:50s} {o['Size']:>8d} bytes")
    if len(contents) > 10:
        print(f"    ... and {len(contents)-10} more")
except Exception as e:
    print(f"\n[S3] ERROR: {e}")

# 4. DynamoDB
ddb = boto3.client('dynamodb')
try:
    table = ddb.describe_table(TableName='alert_history')['Table']
    print(f"\n[DYNAMODB] alert_history: {table['TableStatus']}")
    print(f"  Keys: {json.dumps([k['AttributeName'] for k in table['KeySchema']])}")
except Exception as e:
    print(f"\n[DYNAMODB] ERROR: {e}")

# 5. EventBridge Rules
eb = boto3.client('events')
rules = eb.list_rules()['Rules']
print(f"\n[EVENTBRIDGE] {len(rules)} rules:")
for r in rules:
    targets = eb.list_targets_by_rule(Rule=r['Name'])['Targets']
    target_str = ', '.join([t['Arn'].split(':')[-1] for t in targets])
    print(f"  - {r['Name']:40s} {r['State']:10s} -> {target_str}")

# 6. API Gateways
agw = boto3.client('apigatewayv2')
apis = agw.get_apis()['Items']
print(f"\n[API GATEWAY] {len(apis)} APIs:")
for a in apis:
    routes = agw.get_routes(ApiId=a['ApiId'])['Items']
    route_str = ', '.join([r['RouteKey'] for r in routes])
    print(f"  - {a['Name']:30s} {a['ApiEndpoint']}")
    print(f"    Routes: {route_str}")

# 7. RDS
rds = boto3.client('rds')
instances = rds.describe_db_instances()['DBInstances']
print(f"\n[RDS] {len(instances)} instances:")
for i in instances:
    print(f"  - {i['DBInstanceIdentifier']:30s} {i['DBInstanceStatus']:15s} {i['Engine']} {i.get('EngineVersion','')}")
    print(f"    Endpoint: {i['Endpoint']['Address']}:{i['Endpoint']['Port']}")

print("\n" + "=" * 60)
print("  SCAN COMPLETE")
print("=" * 60)
