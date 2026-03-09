import psycopg2

print("Testing RDS Connection...")
host = "database-1.ckdm4y6i86ke.us-east-1.rds.amazonaws.com"

try:
    conn1 = psycopg2.connect(host=host, port=5432, dbname="floodwatch", user="postgres", password="postgres", connect_timeout=5)
    print("SUCCESS: Password is 'postgres'")
    conn1.close()
except Exception as e:
    print(f"FAILED 'postgres': {e}")

try:
    conn2 = psycopg2.connect(host=host, port=5432, dbname="floodwatch", user="postgres", password="", connect_timeout=5)
    print("SUCCESS: Password is ''")
    conn2.close()
except Exception as e:
    print(f"FAILED '': {e}")
