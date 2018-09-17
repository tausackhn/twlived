import asyncio
from asyncio.runners import _cancel_all_tasks

import pytest


def pytest_runtest_setup(item):
    if 'client_id' in item.keywords and not item.config.getoption('--client-id'):
        pytest.skip('need --client-id to run')
    if 'client_secret' in item.keywords and not item.config.getoption('--client-secret'):
        pytest.skip('need --client-secret to run')


@pytest.yield_fixture(scope='session')
def event_loop(request):
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    try:
        _cancel_all_tasks(loop)
        loop.run_until_complete(loop.shutdown_asyncgens())
    finally:
        asyncio.events.set_event_loop(None)
        loop.close()


@pytest.fixture(scope='module')
def client_id(request):
    return request.config.getoption('--client-id')


@pytest.fixture(scope='module')
def client_secret(request):
    return request.config.getoption('--client-secret')


def bad_calls_list(bad_calls):
    return [(method, args) for method, cases in bad_calls.items() for args in cases]


def bad_calls_ids(bad_calls):
    return [f'{method.__name__}: args={args}, kwargs={list(kwargs.keys())}' for method, cases in bad_calls.items() for
            args, kwargs in cases]
