import boto3
lam = boto3.client('lambda', region_name='us-east-1')

def update_db_pass(func_name, current_env, pass_val):
    env = current_env.copy()
    env["DB_PASS"] = pass_val
    print(f"Updating {func_name} DB_PASS...")
    lam.update_function_configuration(
        FunctionName=func_name,
        Environment={"Variables": env}
    )

funcs = [
    "simulateFloodPropagation",
    "processFloodAlerts"
]

for f in funcs:
    c = lam.get_function(FunctionName=f)["Configuration"]
    env = c.get("Environment", {}).get("Variables", {})
    update_db_pass(f, env, "")

print("Done updating Lambdas.")
