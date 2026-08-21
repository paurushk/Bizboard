# BB-000477 — optional Locust smoke (alternative to k6).
#
#   locust -f load/locust_smoke.py --headless -u 5 -r 1 -t 30s --host http://localhost:8000
#
from locust import HttpUser, task, between


class HealthUser(HttpUser):
    wait_time = between(0.2, 0.8)

    @task
    def health(self):
        self.client.get("/api/v1/health/")
