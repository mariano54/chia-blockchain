import datetime

from typing import List

import pytest

from aiter import map_aiter, push_aiter

from src.remote.RPCStream import RPCStream
from src.remote.json_packaging import (
    make_push_callback,
    msg_for_invocation,
    process_msg_for_obj,
    text_to_target_source_msg,
)


class ExampleAPI:
    async def add(self, a: int, b: int) -> int:
        return a + b

    async def multiple(self, a: int, b: int) -> int:
        return a * b

    async def sum(self, a: List[int]) -> int:
        return sum(a)

    async def day_later(self, now: datetime.datetime) -> datetime.datetime:
        return now + datetime.timedelta(hours=24)


@pytest.mark.asyncio
async def test_remote():

    TO_1 = push_aiter()
    TO_2 = push_aiter()

    async def push_1(o):
        TO_1.push(o)

    async def push_2(o):
        TO_2.push(o)

    example_api = ExampleAPI()

    msg_aiter_in_1 = map_aiter(text_to_target_source_msg, TO_1)
    async_msg_out_callback_1 = make_push_callback(push_2)
    side_1 = RPCStream(
        msg_aiter_in_1,
        async_msg_out_callback_1,
        msg_for_invocation,
        process_msg_for_obj,
    )

    msg_aiter_in_2 = map_aiter(text_to_target_source_msg, TO_2)
    async_msg_out_callback_2 = make_push_callback(push_1)
    side_2 = RPCStream(
        msg_aiter_in_2,
        async_msg_out_callback_2,
        msg_for_invocation,
        process_msg_for_obj,
    )

    for _ in range(50):
        side_1.next_channel()

    side_2.register_local_obj(example_api, 0)

    example_proxy = side_1.remote_obj(ExampleAPI, 0)

    side_1.start()
    side_2.start()

    r = await example_proxy.sum([5, 6, 7])
    assert r == 18
    r = await example_proxy.sum(a=[5000, 6, 7])
    assert r == 5013
    r = await example_proxy.add(5, 6)
    assert r == 11
    r = await example_proxy.add(5, b=6)
    assert r == 11
    now = datetime.datetime(2020, 5, 1, 18, 30, 15)
    later = datetime.datetime(2020, 5, 2, 18, 30, 15)
    r = await example_proxy.day_later(now)
    assert r == later
    r = await example_proxy.day_later(now=now)
    assert r == later

    TO_1.stop()
    TO_2.stop()
    await side_1.await_closed()
    await side_2.await_closed()
