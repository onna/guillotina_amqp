from guillotina_amqp.exceptions import ObjectNotFoundException
from guillotina_amqp.job import Job
from guillotina_amqp.tests.mocks import MockChannel
from guillotina_amqp.tests.mocks import MockEnvelope
from unittest.mock import AsyncMock
from unittest.mock import MagicMock
from unittest.mock import patch

import pytest


func_name = "guillotina_amqp.tests.package.task_foobar_yo"

request_data = {
    "func": func_name,
    "args": [],
    "kwargs": {},
    "db_id": "db",
    "container_id": "gone",
    "task_id": "taskidfoo",
    "req_data": {
        "url": "http://localhost:9090/foo",
        "method": "POST",
        "headers": {"Authorization": "Bearer bar"},
    },
}


def _make_job(base_request=None):
    job = Job(base_request, request_data, MockChannel(), MockEnvelope("uid"))
    job.task = MagicMock()
    return job


async def test_missing_container_is_a_permanent_failure(dummy_request):
    """A container that no longer exists can never be found by retrying.

    create_request must raise the permanent-failure sentinel so __call__
    turns it into an acked no-op.  Raising a bare Exception here instead
    sends the task to the worker's retry path, where it cycles through the
    delay queue forever.
    """
    job = _make_job(base_request=dummy_request)

    context = MagicMock()
    context.async_get = AsyncMock(return_value=None)  # container is gone
    tm = MagicMock()
    tm.begin = AsyncMock()
    tm.get_root = AsyncMock(return_value=context)
    db = MagicMock()
    db.get_transaction_manager.return_value = tm
    root = MagicMock()
    root.async_get = AsyncMock(return_value=db)

    with patch("guillotina_amqp.job.get_utility", return_value=root):
        with pytest.raises(ObjectNotFoundException):
            await job.create_request()


async def test_call_swallows_permanent_failure_from_create_request(dummy_request):
    """create_request runs inside __call__'s try block.

    If it is hoisted out, the `except ObjectNotFoundException` handler can
    never see a failure raised while building the request, and the task is
    retried forever instead of acked.
    """
    job = _make_job()

    with patch(
        "guillotina_amqp.job.Job.create_request",
        new_callable=AsyncMock,
        side_effect=ObjectNotFoundException("Could not find container: gone"),
    ):
        assert await job() is None


async def test_call_still_propagates_unexpected_errors_from_create_request(
    dummy_request,
):
    """Only the permanent-failure sentinel is swallowed.

    Genuinely transient failures while building the request must keep
    reaching the worker so they are retried.
    """
    job = _make_job()

    with patch(
        "guillotina_amqp.job.Job.create_request",
        new_callable=AsyncMock,
        side_effect=RuntimeError("transient boom"),
    ):
        with pytest.raises(RuntimeError):
            await job()
