import psycopg2

conn = psycopg2.connect(dbname="postgres", user="postgres", password="postgres", host="localhost", port=5432)
curs = conn.cursor()

query = "CREATE TABLE IF NOT EXISTS patients (" \
"id VARCHAR PRIMARY KEY," \
"resource_type VARCHAR" \
");"

curs.execute(query)
conn.commit()
curs.close()
conn.close()
print("Table created")