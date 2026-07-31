from guillotina import app_settings
from guillotina_amqp.state import get_state_manager
from guillotina_amqp.state import TaskStatus
from guillotina_amqp.tests.mocks import MockChannel
from guillotina_amqp.tests.mocks import MockEnvelope
from guillotina_amqp.worker import Worker
from unittest.mock import patch

import json
import pytest


async def test_instance_attributes_defaults(dummy_request):
    worker = Worker()
    assert worker._max_running == 10
    assert worker.num_running == 0
    assert worker.total_run == 0
    assert worker.total_errored == 0
    assert worker.sleep_interval == 0.1


async def test_max_task_retries_uses_the_package_default(dummy_request):
    # guillotina_amqp ships a default cap of 5 (see __init__.py). Consumers
    # that set it to null opt into unbounded retries.
    assert Worker().max_task_retries == 5


async def test_max_task_retries_none_disables_the_cap(dummy_request):
    with patch.dict(app_settings["amqp"], {"max_task_retries": None}):
        worker = Worker()

    assert worker.max_task_retries is None


@pytest.mark.parametrize("configured", ["10", 10])
async def test_max_task_retries_is_coerced_to_int(dummy_request, configured):
    """The setting arrives as a str from the environment.

    _handle_unexpected_error compares it against an int retry counter, and a
    str raises TypeError there -- inside a fire-and-forget callback, so the
    message ends up neither acked nor nacked and prefetch eventually starves
    the worker.
    """
    with patch.dict(app_settings["amqp"], {"max_task_retries": configured}):
        worker = Worker()

    assert worker.max_task_retries == 10
    assert isinstance(worker.max_task_retries, int)
    # The comparison in _handle_unexpected_error must not raise.
    assert (0 >= worker.max_task_retries) is False


async def test_worker_acks_canceled_tasks(dummy_request, metrics_registry):
    # Fake some task data
    task_id = "foo"
    task_data = json.dumps({"task_id": task_id, "func": "foo.bar"})

    # Set task as canceled in state
    state_manager = get_state_manager()
    assert await state_manager.cancel(task_id)

    channel = MockChannel()
    assert len(channel.acked) == 0
    envelope = MockEnvelope("footag")

    # Pretend worker picks up the task
    worker = Worker()
    await worker.handle_queued_job(channel, task_data, envelope, None)

    # Check that worker sent ack to amqp channel
    assert len(channel.acked) == 1
    assert channel.acked[0]["kwargs"]["delivery_tag"] == envelope.delivery_tag

    assert (
        metrics_registry.get_sample_value(
            "guillotina_amqp_worker_ops_total",
            {"type": "foo.bar", "status": TaskStatus.CANCELED},
        )
        == 1.0
    )


async def test_worker_acks_already_acquired_tasks(dummy_request, metrics_registry):
    # Fake some task data
    task_id = "foo"
    task_data = json.dumps({"task_id": task_id, "func": "foo.bar"})

    # Mock as if the task would be acquired
    state_manager = get_state_manager()
    await state_manager.acquire(task_id, 900)

    channel = MockChannel()
    assert len(channel.acked) == 0
    envelope = MockEnvelope("footag")

    # Pretend worker picks up the task
    worker = Worker()
    await worker.handle_queued_job(channel, task_data, envelope, None)

    # Check that worker sent ack to amqp channel
    assert len(channel.acked) == 1
    assert channel.acked[0]["kwargs"]["delivery_tag"] == envelope.delivery_tag

    assert (
        metrics_registry.get_sample_value(
            "guillotina_amqp_worker_ops_total",
            {"type": "foo.bar", "status": "alreadyrunning"},
        )
        == 1.0
    )
