# always run Locust with --host pointed at local uvicorn (http://127.0.0.1:8000).
# never point load tests at deployed serverless URLs to avoid violations and unintended costs.

from locust import HttpUser, task, between
import random

class ClinicalUser(HttpUser):
    wait_time = between(0.2, 0.8)

    @task(1)
    def health_check(self):
        self.client.get("/api/health")

    @task(4)
    def view_patients(self):
        limit = random.choice([10, 20, 50])
        gender = random.choice(["male", "female"])
        bmi_cat = random.choice(["Underweight", "Normal", "Overweight", "Obese"])

        query_params = {
            "limit": limit,
            "gender": gender,
            "bmi_category": bmi_cat,
        }

        self.client.get("/api/patients", params=query_params, name="/api/patients")
        
