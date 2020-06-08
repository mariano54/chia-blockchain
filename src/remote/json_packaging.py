"""
This serves as an example for how to stream messages using JSON.

Requests:
{
    s: source_object,  # an integer
    t: target_object,  # an integer, default 0 object used if missing
    m: method_name,
    a: args,  # *args arguments, or [] if missing
    k: kwargs,  # **kwargs arguments, or {} if missing
}

Responses:
{
    t: target_object,  # use the source of the request
    r: return_value,
}
"""

import json

from aiter import map_aiter


from .simple_types import from_simple_types, to_simple_types
from .typecasting import recast_arguments, recast_to_type

from .RPCStream import RPCStream


def msg_for_invocation(method_name, args, kwargs, annotations, source, target):
    """
    This method takes information about an invocation and generates a JSON message.
    """
    args, kwargs = recast_arguments(annotations, to_simple_types, args, kwargs)
    d = dict(m=method_name)
    if args:
        d["a"] = args
    if kwargs:
        d["k"] = kwargs
    if source is not None:
        d["s"] = source
    if target:
        d["t"] = target

    return json.dumps(d)


async def process_msg_for_obj(rpc_stream, msg, obj, source, target):
    """
    This method accepts a message and an object, and handles it.
    There are two cases: the message is a request, or the message is a response.
    """
    # check if request vs response
    if "m" in msg:
        # it's a request

        method = getattr(obj, msg.get("m"), None)
        if method is None:
            raise ValueError(f"no method {method} on {obj}")
        annotations = method.__annotations__

        args, kwargs = recast_arguments(
            annotations, from_simple_types, msg.get("a", []), msg.get("k", {})
        )
        r = await method(*args, **kwargs)

        return_type = annotations.get("return")
        final_r = recast_to_type(r, return_type, to_simple_types)

        d = dict(r=final_r)
        if source:
            d["t"] = source
        return json.dumps(d)

    # it's a response, and obj is a Response
    return_type = obj.return_type
    final_r = recast_to_type(msg.get("r"), return_type, from_simple_types)
    obj.future.set_result(final_r)
    return None


def text_to_target_source_msg(text):
    """
    This method converts a text string into a triple of (json_message, source, target)
    """
    d = json.loads(text)
    source = d.get("s")
    target = d.get("t", 0)
    return source, target, d


def make_push_callback(push):
    """
    This method takes a source, target, msg and turns it into a json message.
    """

    async def push_callback(msg):
        await push(msg)

    return push_callback


def rpc_stream(ws, msg_aiter_in, async_msg_out_callback):
    return RPCStream(
        msg_aiter_in, async_msg_out_callback, msg_for_invocation, process_msg_for_obj
    )


def rpc_stream_for_websocket(ws):
    msg_aiter_in = map_aiter(text_to_target_source_msg, ws)
    async_msg_out_callback = make_push_callback(ws.push)
    return rpc_stream(ws, msg_aiter_in, async_msg_out_callback)


def rpc_stream_for_websocket_aiohttp(ws):
    aiter_1 = map_aiter(lambda _: _.data, ws)
    msg_aiter_in = map_aiter(text_to_target_source_msg, aiter_1)
    async_msg_out_callback = make_push_callback(ws.send_str)
    return rpc_stream(ws, msg_aiter_in, async_msg_out_callback)
