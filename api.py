import uvicorn, psycopg2
from psycopg2.extras import RealDictCursor
from fastapi import FastAPI

app = FastAPI(title="FHIR Pipeline")

@app.get("/")
def home():
    return {"key": "value"}

@app.get("/patients")
def get_patients():
    conn = psycopg2.connect(
        dbname="postgres", 
        user="postgres", 
        password="postgres", 
        host="localhost", 
        port=5432
        )
    curs = conn.cursor(cursor_factory=RealDictCursor)
    query = "SELECT * FROM patients;"
    try:
        curs.execute(query)
        results = curs.fetchall()

        print(f"Total results found: {len(results)}")
        print("-"*30)

        for row in results:
            print(row)
    finally:
        curs.close()
        conn.close()
    
    return {"patients": results}

