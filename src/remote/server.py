import logging

from aiohttp import web

from src.remote.json_packaging import rpc_stream_for_websocket_aiohttp

log = logging.getLogger(__name__)


def create_routes_for_ws_obj_server(ws_uri, ws_callback):
    routes = web.RouteTableDef()

    @routes.get(ws_uri)
    async def ws_request(request):
        ws = web.WebSocketResponse()
        await ws.prepare(request)
        await ws_callback(ws)
        return ws

    return routes


async def create_unix_site(runner, path):
    site = web.UnixSite(runner, path)
    await site.start()
    return site, path


async def create_tcp_site(runner, start_port, last_port=None):
    port = start_port
    if last_port is None:
        last_port = start_port + 1
    while port < last_port:
        host = "127.0.0.1"
        site = web.TCPSite(runner, port=port, host=host)
        try:
            await site.start()
            break
        except IOError:
            port += 1
    else:
        raise RuntimeError("couldn't find a port to listen on")
    return site, port


async def create_object_server(obj, ws_uri, create_site_callback):
    """
    `create_site_callback` is an async callback that takes `runner`. It should
    probably just use one of `create_unix_site` or `create_tcp_site`.
    """

    async def ws_callback(ws):
        rpc_stream = rpc_stream_for_websocket_aiohttp(ws)
        rpc_stream.register_local_obj(obj, 0)
        rpc_stream.start()
        await rpc_stream.await_closed()

    routes = create_routes_for_ws_obj_server(ws_uri, ws_callback)

    app = web.Application()
    app.add_routes(routes)

    runner = web.AppRunner(app)
    await runner.setup()

    site, where = await create_site_callback(runner)

    app["site"] = site

    return site, where
