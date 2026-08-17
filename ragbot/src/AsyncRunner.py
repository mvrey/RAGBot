"""A single long-lived event loop for running agent calls.

`asyncio.run()` closes its event loop when it returns. The Google (and OpenAI)
clients underneath pydantic-ai hold a persistent httpx connection pool bound to
whichever loop first used it, so a second `asyncio.run()` fails with
"RuntimeError: Event loop is closed" as the pool touches the dead loop.

Keeping one loop alive on its own thread for the process lifetime avoids that, and
lets connections be reused across turns instead of being rebuilt each time.
"""

import asyncio
import threading


class AsyncRunner:
    """Runs coroutines on a private event loop owned by a dedicated thread."""

    def __init__(self):
        self._loop = asyncio.new_event_loop()
        self._ready = threading.Event()
        self._thread = threading.Thread(
            target=self._run_forever, name="ragbot-asyncio", daemon=True
        )
        self._thread.start()
        # Don't hand out the runner until the loop is actually spinning.
        self._ready.wait(timeout=5)

    def _run_forever(self):
        asyncio.set_event_loop(self._loop)
        self._loop.call_soon(self._ready.set)
        self._loop.run_forever()

    def run(self, coro, timeout: float = None):
        """Run a coroutine on the shared loop and block until it finishes."""
        if self._loop.is_closed():
            raise RuntimeError("AsyncRunner has been closed.")
        return asyncio.run_coroutine_threadsafe(coro, self._loop).result(timeout)

    def close(self):
        if self._loop.is_closed():
            return
        self._loop.call_soon_threadsafe(self._loop.stop)
        self._thread.join(timeout=5)
        self._loop.close()
