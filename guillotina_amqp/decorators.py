from functools import partial
from guillotina.transactions import get_transaction
from guillotina.utils import get_current_request
from guillotina_amqp.interfaces import ITaskDefinition
from guillotina_amqp.utils import add_object_task
from guillotina_amqp.utils import add_task
from zope.interface import implementer

import uuid


@implementer(ITaskDefinition)
class TaskDefinition:
    def __init__(self, func, retries=3, dest_queue=None):
        self.func = func
        self.retries = retries
        self.dest_queue = dest_queue

    async def __call__(self, *args, _request=None, **kwargs):
        return await add_task(
            self.func,
            _request=_request,
            _retries=self.retries,
            dest_queue=self.dest_queue,
            *args,
            **kwargs
        )

    schedule = __call__

    def _get_request(self, request, kwargs):
        if request is None:
            if "request" in kwargs:
                request = kwargs["request"]
            else:
                request = get_current_request()
        return request

    def after_request(self, *args, _request=None, _name=None, **kwargs) -> str:
        request = self._get_request(_request, kwargs)
        kwargs["_request"] = request
        if _name is None:
            _name = str(uuid.uuid4())
        request.add_future(_name, partial(self.schedule, *args, **kwargs))
        return _name

    def after_commit(self, *args, _request=None, **kwargs):
        txn = get_transaction()
        txn.add_after_commit_hook(partial(self.schedule, *args, **kwargs))

    def before_commit(self, *args, _request=None, **kwargs):
        txn = get_transaction()
        txn.add_before_commit_hook(partial(self.schedule, *args, **kwargs))


class ObjectTaskDefinition(TaskDefinition):
    async def __call__(self, *args, _request=None, **kwargs):
        return await add_object_task(
            self.func,
            _request=_request,
            _retries=self.retries,
            dest_queue=self.dest_queue,
            *args,
            **kwargs
        )

    schedule = __call__


def task(func=None, retries=3, dest_queue=None):
    if func is not None:
        return TaskDefinition(func, retries=retries, dest_queue=dest_queue)

    def wrapper(f):
        return TaskDefinition(f, retries=retries, dest_queue=dest_queue)

    return wrapper


def object_task(func=None, retries=3, dest_queue=None):
    if func is not None:
        return ObjectTaskDefinition(func, retries=retries, dest_queue=dest_queue)

    def wrapper(f):
        return ObjectTaskDefinition(f, retries=retries, dest_queue=dest_queue)

    return wrapper
