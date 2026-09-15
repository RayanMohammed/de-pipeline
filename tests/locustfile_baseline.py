# A separate load-test target from locustfile.py on purpose: every task in
# here hits an endpoint that never touches Depends(get_db) or the connection
# pool, so it measures the raw ceiling of uvicorn + FastAPI's request handling
# with zero database involvement. Run this and locustfile.py as two SEPARATE
# Locust runs (not combined into one file) so their stats don't get averaged
# together -- the whole point is comparing the two numbers side by side.
#
# Same rule as locustfile.py: only run against local uvicorn, never a deployed URL.

from locust import HttpUser, task, between

class NoDbBaselineUser(HttpUser):
    wait_time = between(0.2, 0.8)

    @task
    def openapi_schema(self):
        self.client.get("/openapi.json")
