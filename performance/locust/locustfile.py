"""Local load scenarios for Secure Backend Platform."""

import os
import uuid
from urllib.parse import urlparse

from locust import HttpUser, between, constant_throughput, task


class BackendUser(HttpUser):
    """Exercise authenticated API reads and simulated payments."""

    hold_rpm = os.getenv("LOCUST_HOLD_RPM")
    wait_time = constant_throughput(float(hold_rpm) / 60) if hold_rpm else between(1, 2)

    def on_start(self) -> None:
        host = urlparse(self.host or "")
        if host.hostname not in {"localhost", "127.0.0.1"}:
            raise RuntimeError("Locust MVP permits localhost only")

        username = os.environ.get("FIRST_SUPERUSER")
        password = os.environ.get("FIRST_SUPERUSER_PASSWORD")

        if not username or not password:
            raise RuntimeError("Missing Locust login credentials")

        with self.client.post(
            "/api/v1/login/access-token",
            data={"username": username, "password": password},
            name="POST /login/access-token",
            catch_response=True,
        ) as response:
            if response.status_code != 200:
                response.failure(f"Login HTTP {response.status_code}")
                raise RuntimeError("Locust authentication failed")

            try:
                token = response.json()["access_token"]
            except (ValueError, KeyError, TypeError) as exc:
                response.failure("Login response missing access_token")
                raise RuntimeError("Invalid login response") from exc

            response.success()

        self.headers = {"Authorization": f"Bearer {token}"}

    @task(5)
    def read_items(self) -> None:
        with self.client.get(
            "/api/v1/items/",
            headers=self.headers,
            name="GET /items/",
            catch_response=True,
        ) as response:
            if response.status_code != 200:
                response.failure(f"Unexpected HTTP {response.status_code}")
                return

            try:
                data = response.json()
            except ValueError:
                response.failure("Invalid JSON response")
                return

            if not isinstance(data, dict) or not isinstance(data.get("data"), list):
                response.failure("Invalid items response")

    @task(2)
    def payment_success(self) -> None:
        self._payment("success", "PAID")

    @task(1)
    def payment_declined(self) -> None:
        self._payment("declined", "FAILED")

    @task(1)
    def invalid_token(self) -> None:
        with self.client.get(
            "/api/v1/items/",
            headers={"Authorization": "Bearer invalid-token"},
            name="GET /items/ [invalid token]",
            catch_response=True,
        ) as response:
            if response.status_code != 403:
                response.failure(f"Expected HTTP 403, got {response.status_code}")
                return

            response.success()

    def _payment(self, scenario: str, expected_status: str) -> None:
        order_id = f"locust-{uuid.uuid4().hex}"

        with self.client.post(
            f"/api/v1/orders/{order_id}/payments",
            headers=self.headers,
            json={"amount": 1250, "scenario": scenario},
            name=f"POST /orders/{{id}}/payments [{scenario}]",
            catch_response=True,
        ) as response:
            if response.status_code != 200:
                response.failure(f"Unexpected HTTP {response.status_code}")
                return

            try:
                status = response.json()["status"]
            except (ValueError, KeyError, TypeError):
                response.failure("Invalid payment response")
                return

            if status != expected_status:
                response.failure(f"Expected {expected_status}, got {status}")
