from guillotina import task_vars
from guillotina.utils import get_dotted_name
from guillotina_amqp.job import Job
from guillotina_amqp.state import TaskState
from guillotina_amqp.state import TaskStatus
from guillotina_amqp.tests.utils import _decorator_test_func
from guillotina_amqp.tests.utils import _test_asyncgen
from guillotina_amqp.tests.utils import _test_asyncgen_doubley
from guillotina_amqp.tests.utils import _test_asyncgen_invalid
from guillotina_amqp.tests.utils import _test_delay_queue
from guillotina_amqp.tests.utils import _test_failing_func
from guillotina_amqp.tests.utils import _test_func
from guillotina_amqp.tests.utils import _test_long_func
from guillotina_amqp.utils import _run_object_task
from guillotina_amqp.utils import _yield_object_task
from guillotina_amqp.utils import add_task
from guillotina_amqp.utils import cancel_task

import asyncio
import json
import time


async def test_add_task(
    dummy_request,
    rabbitmq_container,
    amqp_worker,
    amqp_channel,
    configured_state_manager,
):
    task_vars.request.set(dummy_request)
    ts = await add_task(_test_func, 1, 2)

    await ts.join(0.02)
    await asyncio.sleep(1)

    state = await ts.get_state()
    assert state["status"] == TaskStatus.FINISHED
    main_queue = await amqp_worker.queue_main(amqp_channel)
    assert main_queue["message_count"] == 0

    task_vars.request.set(None)


async def test_add_task_to_specific_queue(
    dummy_request,
    rabbitmq_container,
    amqp_worker,
    amqp_channel,
    configured_state_manager,
):

    new_queue = "new_queue" + str(time.time())

    # Declare a new queue
    new_queue_info = await amqp_channel.queue_declare(
        queue_name=new_queue,
        durable=True,
        passive=False,
        arguments={
            "x-dead-letter-exchange": amqp_worker.MAIN_EXCHANGE,
            "x-dead-letter-routing-key": new_queue,
            "x-message-ttl": amqp_worker.TTL_DELAYED,
        },
    )

    await amqp_channel.queue_bind(
        exchange_name=amqp_worker.MAIN_EXCHANGE,
        queue_name=new_queue,
        routing_key=new_queue,
    )

    await asyncio.sleep(1)
    assert new_queue_info["message_count"] == 0

    task_vars.request.set(dummy_request)
    await add_task(_test_func, 1, 2, dest_queue=new_queue)

    new_queue_info = await amqp_channel.queue_declare(
        queue_name=new_queue,
        durable=True,
        passive=False,
        arguments={
            "x-dead-letter-exchange": amqp_worker.MAIN_EXCHANGE,
            "x-dead-letter-routing-key": new_queue,
            "x-message-ttl": amqp_worker.TTL_DELAYED,
        },
    )

    await asyncio.sleep(1)
    assert new_queue_info["message_count"] == 1


async def test_generator_tasks(
    dummy_request,
    rabbitmq_container,
    amqp_worker,
    amqp_channel,
    configured_state_manager,
):
    task_vars.request.set(dummy_request)
    ts = await add_task(_test_asyncgen, 1, 2)
    await ts.join(0.02)

    state = await ts.get_state()
    assert state["status"] == TaskStatus.FINISHED
    assert "Yellow" in state["eventlog"][-1]
    assert await ts.get_result() == [3]
    main_queue = await amqp_worker.queue_main(amqp_channel)
    assert main_queue["message_count"] == 0

    ts_invalid = await add_task(_test_asyncgen_invalid)
    await ts_invalid.join(0.02)
    assert await ts_invalid.get_result() is None

    ts_doubley = await add_task(_test_asyncgen_doubley, 128, 1024, 2048)
    await ts_doubley.join(0.02)
    assert await ts_doubley.get_result() == [128, 1024, 2048]

    task_vars.request.set(None)


async def test_run_task(dummy_request, rabbitmq_container, amqp_worker):
    task_vars.request.set(dummy_request)
    state = await add_task(_test_func, 1, 2)
    await state.join(0.01)
    await asyncio.sleep(0.1)  # prevent possible race condition here
    assert amqp_worker.total_run == 1
    assert await state.get_result() == 3
    task_vars.request.set(None)


async def test_task_from_service(rabbitmq_container, amqp_worker, container_requester):
    async with container_requester as requester:
        resp, _ = await requester("GET", "/db/guillotina/@foobar")
        state = TaskState(resp["task_id"])
        await state.join(0.01)
        assert await state.get_result() == 3
        await asyncio.sleep(0.1)  # prevent possible race condition here
        assert amqp_worker.total_run == 1


async def test_task_commits_data_from_service(
    rabbitmq_container, amqp_worker, container_requester
):
    async with container_requester as requester:
        await requester(
            "POST",
            "/db/guillotina",
            data=json.dumps({"@type": "Item", "id": "foobar", "title": "blah"}),
        )
        resp, _ = await requester("GET", "/db/guillotina/foobar/@foobar-write")
        state = TaskState(resp["task_id"])
        await state.join(0.01)
        assert await state.get_result() == "done!"
        await asyncio.sleep(0.1)  # prevent possible race condition here
        assert amqp_worker.total_run == 1
        resp, status = await requester("GET", "/db/guillotina/foobar")
        assert resp["title"] == "Foobar written"


async def test_async_gen_task_commits_data_from_service(
    configured_state_manager, rabbitmq_container, amqp_worker, container_requester
):
    async with container_requester as requester:
        await requester(
            "POST",
            "/db/guillotina",
            data=json.dumps({"@type": "Item", "id": "foobar", "title": "blah"}),
        )
        resp, _ = await requester(
            "GET", "/db/guillotina/foobar/@foobar-write-async-gen"
        )
        state = TaskState(resp["task_id"])
        await state.join(0.01)
        assert await state.get_status() == "finished"
        task_state = await state.get_state()
        assert len(task_state["eventlog"]) == 3
        assert await state.get_result() == ["one", "two", "final"]
        await asyncio.sleep(0.1)  # prevent possible race condition here
        assert amqp_worker.total_run == 1
        resp, status = await requester("GET", "/db/guillotina/foobar")
        assert resp["title"] == "CHANGED!"


async def test_cancels_long_running_task(
    dummy_request, rabbitmq_container, amqp_worker, configured_state_manager
):
    task_vars.request.set(dummy_request)
    # Add long running task
    ts = await _test_long_func(120)
    # Wait a bit and cancel
    await asyncio.sleep(1)
    success = await cancel_task(ts.task_id)
    assert success
    # Wait until worker sees task is cancelled and cancels the
    # asycio task
    await ts.join(0.2)

    # Check that the it was indeed cancelled
    state = await ts.get_state()
    assert state["status"] == TaskStatus.CANCELED
    await asyncio.sleep(0.1)  # prevent possible race condition here
    assert amqp_worker.total_run == 1
    task_vars.request.set(None)


async def test_decorator_task(dummy_request, rabbitmq_container, amqp_worker):
    task_vars.request.set(dummy_request)
    state = await _decorator_test_func(1, 2)
    data = await state.join(0.01)
    assert data["result"] == 3
    await asyncio.sleep(0.1)  # prevent possible race condition here
    assert amqp_worker.total_run == 1
    assert await state.get_status() == "finished"
    assert await state.get_result() == 3
    task_vars.request.set(None)


async def test_errored_job_should_be_published_to_delayed_queue(
    dummy_request, rabbitmq_container, amqp_worker, amqp_channel
):
    task_vars.request.set(dummy_request)
    ts = await _test_failing_func()
    # wait for it to finish
    await ts.join(0.1)
    amqp_worker.max_task_retries = 5
    assert amqp_worker.total_run == 1
    await amqp_worker.join()
    state = await ts.get_state()
    assert state["status"] == TaskStatus.ERRORED
    assert state["job_retries"] == 1

    task_id = state["job_data"]["task_id"]

    # Check that the job has been moved to the delay queue and
    # verify the task id

    delayed = await amqp_worker.queue_delayed(amqp_channel)
    assert delayed["message_count"] == 1

    async def callback(channel, body, envelope, properties):
        decoded = json.loads(body)
        assert decoded["task_id"] == task_id

    await amqp_channel.basic_consume(callback, queue_name=delayed["queue"])
    task_vars.request.set(None)


async def test_worker_does_not_nack_when_max_retries_is_null(
    dummy_request, rabbitmq_container, amqp_worker, amqp_channel
):
    task_vars.request.set(dummy_request)

    # Add failing function and wait for it to finish
    ts = await _test_failing_func()

    amqp_worker.max_task_retries = None
    current_retries = 999
    await amqp_worker.state_manager.update(ts.task_id, {"job_retries": current_retries})

    # Wait for it to finish
    await ts.join(0.1)

    # Check that worker ran only once
    assert amqp_worker.total_run == 1

    # Check that it retries again
    state = await ts.get_state()
    retried = state["job_retries"]
    assert retried == current_retries + 1

    # Check that it went to delay queue
    delay_queue = await amqp_worker.queue_delayed(amqp_channel)
    assert delay_queue["message_count"] > 1

    task_vars.request.set(None)


async def test_worker_retries_should_not_exceed_the_limit(
    dummy_request, rabbitmq_container, amqp_worker, amqp_channel, metrics_registry
):
    task_vars.request.set(dummy_request)

    # Add failing function and wait for it to finish
    ts = await _test_failing_func()

    # Fake job retries to max
    amqp_worker.max_task_retries = 5
    max_retries = amqp_worker.max_task_retries
    await amqp_worker.state_manager.update(ts.task_id, {"job_retries": max_retries})
    # Wait for it to finish
    await ts.join(0.1)
    # Check that worker ran only one
    assert amqp_worker.total_run == 1
    await amqp_worker.join()

    # Check that it retries up to max
    state = await ts.get_state()
    retried = state["job_retries"]
    assert retried == max_retries

    # Check that it went to error queue
    main_queue = await amqp_worker.queue_main(amqp_channel)
    errored_queue = await amqp_worker.queue_errored(amqp_channel)
    assert main_queue["consumer_count"] == 1
    assert errored_queue["message_count"] == 1

    task_vars.request.set(None)

    assert (
        metrics_registry.get_sample_value(
            "guillotina_amqp_worker_ops_total",
            {
                "type": "guillotina_amqp.tests.utils._test_failing_func",
                "status": TaskStatus.RUNNING,
            },
        )
        == 1.0
    )
    assert (
        metrics_registry.get_sample_value(
            "guillotina_amqp_worker_ops_total",
            {
                "type": "guillotina_amqp.tests.utils._test_failing_func",
                "status": TaskStatus.ERRORED,
            },
        )
        == 1.0
    )


async def test_worker_sends_noop_tasks_after_inactivity(
    dummy_request, rabbitmq_container, amqp_worker, amqp_channel
):
    task_vars.request.set(dummy_request)

    # Simulate some time without activity
    await asyncio.sleep(1)
    initial_last_activity = amqp_worker.last_activity
    assert time.time() - initial_last_activity > 1

    # Start check activity task
    amqp_worker._check_activity = True
    amqp_worker._activity_task = asyncio.ensure_future(
        amqp_worker.check_activity(check_every=0.3, noop_after=1, kill_after=500)
    )

    # Wait a bit for activity task to send NOOP
    await asyncio.sleep(1.5)

    # Check that the noop message triggered last_activity to update,
    # which means NOOP task was received and executed
    assert amqp_worker.last_activity > initial_last_activity

    task_vars.request.set(None)


async def test_delay_task_exception_should_be_published_to_delay_queue(
    dummy_request, rabbitmq_container, amqp_worker, amqp_channel
):
    task_vars.request.set(dummy_request)
    ts = await _test_delay_queue()
    # wait for it to finish
    await ts.join(0.1)
    amqp_worker.max_task_retries = 5
    assert amqp_worker.total_run == 1
    await amqp_worker.join()
    state = await ts.get_state()
    assert state["status"] == TaskStatus.SLEEPING

    task_id = state["job_data"]["task_id"]

    # Check that the job has been moved to the delay queue and
    # verify the task id

    delayed = await amqp_worker.queue_delayed(amqp_channel)
    # we want greater than 2 since 2 other delay queue messages are there
    assert delayed["message_count"] > 2

    async def callback(channel, body, envelope, properties):
        decoded = json.loads(body)
        assert decoded["task_id"] == task_id

    await amqp_channel.basic_consume(callback, queue_name=delayed["queue"])
    task_vars.request.set(None)


def test_job_function_name():
    data = {"func": get_dotted_name(_run_object_task), "args": ["my.func.foobar"]}
    job = Job(None, data, None, None)
    assert job.function_name == "run_object_task/my.func.foobar"

    data = {"func": get_dotted_name(_yield_object_task), "args": ["my.func.foobar"]}
    job = Job(None, data, None, None)
    assert job.function_name == "yield_object_task/my.func.foobar"

    data = {"func": get_dotted_name(_test_func), "args": []}
    job = Job(None, data, None, None)
    assert job.function_name == "guillotina_amqp.tests.utils._test_func"

    data = {"func": "does.not.exist", "args": []}
    job = Job(None, data, None, None)
    assert job.function_name == "does.not.exist"
