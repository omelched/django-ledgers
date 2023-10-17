import functools
from threading import Thread

from django.db import connection


class ThreadWithContext(Thread):
    def __init__(self, context=None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.context = context or {}

    def run(self) -> None:
        res = None

        try:
            if self._target is not None:
                res = self._target(*self._args, **self._kwargs)
        except Exception as e:
            self.context['state'] = 'FAILED'
            self.context['exception'] = e
        else:
            self.context['state'] = 'SUCCESS'
            self.context['result'] = res
        finally:
            del self._target, self._args, self._kwargs


def concurrent_transaction(fn):
    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        thread = ThreadWithContext(target=fn)
        thread.start()
        if thread.is_alive():
            thread.join()

        if thread.context['state'] == 'FAILED':
            raise thread.context['exception']
        else:
            return thread.context['result']

    # SQLite does not support concurrency
    if connection.vendor == 'sqlite':
        return fn
    else:
        return wrapper
