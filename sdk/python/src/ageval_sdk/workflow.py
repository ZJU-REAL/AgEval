"""Bounded async helpers — no Run/Trial/Campaign authority."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Iterable, Sequence
from typing import Any


async def bounded_gather[T](
    aws: Sequence[Awaitable[T]],
    *,
    limit: int,
) -> list[T | BaseException]:
    if limit < 1:
        raise ValueError("limit must be >= 1")
    sem = asyncio.Semaphore(limit)
    results: list[T | BaseException] = []

    async def run_one(aw: Awaitable[T]) -> T | BaseException:
        async with sem:
            try:
                return await aw
            except BaseException as exc:  # noqa: BLE001
                return exc

    tasks = [asyncio.create_task(run_one(aw)) for aw in aws]
    try:
        for t in tasks:
            results.append(await t)
    finally:
        for t in tasks:
            if not t.done():
                t.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
    return results


async def first_success[T](aws: Iterable[Awaitable[T]]) -> T:
    tasks = [asyncio.create_task(aw) for aw in aws]
    try:
        while tasks:
            done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
            for d in done:
                tasks.remove(d)
                exc = d.exception()
                if exc is None:
                    for p in pending:
                        p.cancel()
                    if pending:
                        await asyncio.gather(*pending, return_exceptions=True)
                    return d.result()
            # all done so far failed — continue if pending
        raise RuntimeError("all failed")
    finally:
        for t in tasks:
            if not t.done():
                t.cancel()


async def collect_results(values: Sequence[Any]) -> list[Any]:
    out: list[Any] = []
    for v in values:
        if hasattr(v, "__await__"):
            out.append(await v)  # type: ignore[misc]
        else:
            out.append(v)
    return out
