from guillotina_amqp.job import Job
from guillotina_amqp.tests.mocks import MockChannel
from guillotina_amqp.tests.mocks import MockEnvelope
from unittest.mock import MagicMock

from unittest.mock import AsyncMock
from unittest.mock import patch
import pytest


func_name = "guillotina_amqp.tests.package.task_foobar_yo"

request_data = {
    "func": func_name,
    "task_id": "taskidfoo",
    "req_data": {
        "url": "http://localhost:9090/foo",
        "method": "POST",
        "headers": {"Authorization": "Bearer bar"},
    },
}


@pytest.fixture(scope="function")
def patched_job():
    mock_request = MagicMock()
    with patch(
        "guillotina_amqp.job.Job.create_request",
        new_callable=AsyncMock,
        return_value=mock_request,
    ):
        with patch("guillotina_amqp.job.Job._Job__run", new_callable=AsyncMock):
            yield


class TestJobMetrics:
    async def test_job_metrics(self, metrics_registry, patched_job):
        job = Job(None, request_data, MockChannel(), MockEnvelope("uid"))
        job.task = MagicMock()

        await job()
        assert (
            metrics_registry.get_sample_value(
                "guillotina_amqp_job_request_ops_total", {"error": "none"}
            )
            == 1.0
        )
        assert (
            metrics_registry.get_sample_value(
                "guillotina_amqp_job_request_ops_time_seconds_sum",
            )
            > 0
        )

        assert (
            metrics_registry.get_sample_value(
                "guillotina_amqp_job_ops_total", {"type": func_name, "error": "none"}
            )
            == 1.0
        )
        assert (
            metrics_registry.get_sample_value(
                "guillotina_amqp_job_ops_processing_time_seconds_sum",
                {"type": func_name},
            )
            > 0
        )

        assert (
            metrics_registry.get_sample_value(
                "guillotina_amqp_job_commit_ops_total",
                {"type": func_name, "error": "none"},
            )
            == 1.0
        )
        assert (
            metrics_registry.get_sample_value(
                "guillotina_amqp_job_commit_ops_time_seconds_sum", {"type": func_name}
            )
            > 0
        )
