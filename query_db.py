import psycopg2

conn = psycopg2.connect(dbname="postgres", user="postgres", password="postgres", host="localhost", port=5432)
curs = conn.cursor()
query = "SELECT * FROM patients;"

curs.execute(query)
results = curs.fetchall()

print(f"Total results found: {len(results)}")
print("-"*30)

for row in results:
    print(row)

curs.close()
conn.close()