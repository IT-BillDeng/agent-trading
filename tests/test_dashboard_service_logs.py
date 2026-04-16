import asyncio
import unittest
from types import SimpleNamespace
from unittest import mock

from fastapi.responses import JSONResponse

from dashboard import main as dashboard_main


class DashboardServiceLogTests(unittest.TestCase):
    def test_dashboard_middleware_logs_server_errors(self):
        request = SimpleNamespace(
            method="GET",
            url=SimpleNamespace(path="/__test_500", query=""),
        )

        async def call_next(_request):
            return JSONResponse({"error": "boom"}, status_code=500)

        with mock.patch.object(dashboard_main, "append_service_log") as log_mock:
            response = asyncio.run(dashboard_main.log_service_exceptions(request, call_next))

        self.assertEqual(response.status_code, 500)
        log_mock.assert_called_once()
        _, kwargs = log_mock.call_args
        self.assertEqual(kwargs["kind"], "request_error")
        self.assertEqual(kwargs["path"], "/__test_500")
        self.assertEqual(kwargs["status_code"], 500)


if __name__ == "__main__":
    unittest.main()
