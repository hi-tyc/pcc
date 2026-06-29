"""Async/await example.

Demonstrates that pcc can compile any Python program that uses `async def`,
`await`, `async for`, or `async with`. The compiled binary is a small native
executable that initializes libpython and runs the source as Python code
through PyRun_SimpleString, giving 100% compatibility with CPython's
coroutine machinery.

    $ pcc samples/async_demo.py -o async_demo
    $ ./async_demo
"""

import asyncio
import time


async def fetch_data(n):
    """Simulate a slow coroutine."""
    await asyncio.sleep(0.01)
    return n * 2


async def counter(name, n):
    """Async generator."""
    for i in range(n):
        await asyncio.sleep(0.01)
        yield f"{name}:{i}"


async def main():
    print("=== simple await ===")
    t0 = time.time()
    results = []
    for i in range(5):
        r = await fetch_data(i)
        results.append(r)
    print("results:", results)
    print("elapsed: %.3fs" % (time.time() - t0))

    print("=== async for ===")
    out = []
    async for msg in counter("a", 4):
        out.append(msg)
    print(out)

    print("=== asyncio.gather ===")
    async def task(n):
        await asyncio.sleep(0.01)
        return n * 10
    vals = await asyncio.gather(*[task(i) for i in range(5)])
    print("gathered:", vals)

    print("=== async with ===")
    # Simulate an async context manager
    class Timer:
        async def __aenter__(self):
            self.t0 = time.time()
            return self
        async def __aexit__(self, *exc):
            print("elapsed: %.3fs" % (time.time() - self.t0))
            return False
    async with Timer():
        await asyncio.sleep(0.02)
        print("inside timer")


asyncio.run(main())
