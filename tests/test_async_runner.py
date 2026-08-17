import asyncio

import pytest

from src.AsyncRunner import AsyncRunner


@pytest.fixture
def runner():
    r = AsyncRunner()
    yield r
    r.close()


async def _echo(value):
    await asyncio.sleep(0)
    return value


class TestAsyncRunner:

    def test_runs_a_coroutine(self, runner):
        assert runner.run(_echo(42)) == 42

    def test_reuses_one_loop_across_calls(self, runner):
        async def current_loop():
            return id(asyncio.get_running_loop())

        # The whole point: a stable loop, so pooled HTTP connections stay valid.
        assert runner.run(current_loop()) == runner.run(current_loop())

    def test_loop_stays_open_between_calls(self, runner):
        # Regression: asyncio.run() closed its loop, so the second agent call died
        # with "Event loop is closed" once a pooled client touched the dead loop.
        async def loop_is_open():
            return not asyncio.get_running_loop().is_closed()

        for _ in range(5):
            assert runner.run(loop_is_open())

    def test_a_resource_bound_to_the_loop_survives_calls(self, runner):
        # Stands in for an httpx pool: created on the loop, used on a later call.
        async def make_event():
            return asyncio.Event()

        event = runner.run(make_event())

        async def use_event():
            event.set()
            return event.is_set()

        assert runner.run(use_event())

    def test_propagates_exceptions(self, runner):
        async def boom():
            raise ValueError("kaboom")

        with pytest.raises(ValueError, match="kaboom"):
            runner.run(boom())

    def test_failure_does_not_poison_the_loop(self, runner):
        async def boom():
            raise ValueError("kaboom")

        with pytest.raises(ValueError):
            runner.run(boom())

        assert runner.run(_echo("still working")) == "still working"

    def test_respects_a_timeout(self, runner):
        async def slow():
            await asyncio.sleep(5)

        with pytest.raises(TimeoutError):
            runner.run(slow(), timeout=0.1)

    def test_runs_on_a_background_thread(self, runner):
        import threading

        async def thread_name():
            return threading.current_thread().name

        assert runner.run(thread_name()) == "ragbot-asyncio"

    def test_close_is_idempotent(self):
        r = AsyncRunner()
        r.close()
        r.close()

    def test_running_after_close_raises(self):
        r = AsyncRunner()
        r.close()

        coro = _echo(1)
        try:
            with pytest.raises(RuntimeError, match="closed"):
                r.run(coro)
        finally:
            coro.close()  # never awaited, since run() rejected it
