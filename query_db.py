import psycopg2

conn = psycopg2.connect(dbname="postgres", user="postgres", password="postgres", host="localhost", port=5432)
curs = conn.cursor()
query = "SELECT * FROM patients;"

curs.execute(query)
results = curs.fetchall()
for item in results:
    print(item)

curs.close()
conn.close()