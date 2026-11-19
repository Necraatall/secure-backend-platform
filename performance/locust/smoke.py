"""Minimal independent FastAPI health-check smoke test."""

from locust import HttpUser, constant, task


class HealthCheckSmoke(HttpUser):
    """Verify that the backend health endpoint responds correctly."""

    wait_time = constant(1)

    @task
    def health_check(self) -> None:
        with self.client.get(
            "/api/v1/utils/health-check/",
            name="GET /health-check/",
            catch_response=True,
        ) as response:
            if response.status_code != 200:
                response.failure(f"Expected HTTP 200, got {response.status_code}")
                return

            if response.text.strip() != "true":
                response.failure("Expected JSON boolean true")
