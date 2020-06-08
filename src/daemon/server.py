import asyncio
import logging

from aiohttp import web

from src.cmds.init import chia_init

from src.util.config import load_config
from src.util.logging import initialize_logging
from src.util.path import mkdir

from src.remote.json_packaging import rpc_stream_for_websocket_aiohttp

from .client import (
    connect_to_daemon_and_validate,
    socket_server_path,
    should_use_unix_socket,
)
from .daemon_api import DaemonAPI
from .singleton import singleton

log = logging.getLogger(__name__)


def daemon_launch_lock_path(root_path):
    """
    A path to a file that is lock when a daemon is launching but not yet started.
    This prevents multiple instances from launching.
    """
    return root_path / "run" / "start-daemon.launching"


def create_server_for_daemon(root_path, ws_callback):
    routes = web.RouteTableDef()

    @routes.get("/ws/")
    async def ws_request(request):
        ws = web.WebSocketResponse()
        await ws.prepare(request)
        await ws_callback(ws)
        return ws

    app = web.Application()
    app.add_routes(routes)
    return app


async def create_site_for_daemon(runner, path, start_port):
    if should_use_unix_socket():
        site = web.UnixSite(runner, path)
        await site.start()
        return site, path

    port = start_port
    while port < 65536:
        host = "127.0.0.1"
        site = web.TCPSite(runner, port=port, host=host)
        try:
            await site.start()
            with open(path, "w") as f:
                f.write(f"{port}\n")
            break
        except IOError:
            port += 1
    else:
        raise RuntimeError("couldn't find a port to listen on")
    return site, port


async def async_run_daemon(root_path):
    chia_init(root_path)
    config = load_config(root_path, "config.yaml")
    initialize_logging("daemon %(name)-25s", config["logging"], root_path)

    daemon_api = DaemonAPI(root_path)

    async def ws_callback(ws):
        rpc_stream = rpc_stream_for_websocket_aiohttp(ws)
        rpc_stream.register_local_obj(daemon_api, 0)
        rpc_stream.start()
        await rpc_stream.await_closed()

    connection = await connect_to_daemon_and_validate(root_path)
    if connection is not None:
        print("daemon: already running")
        return 1

    lockfile = singleton(daemon_launch_lock_path(root_path))
    if lockfile is None:
        print("daemon: already launching")
        return 2

    app = create_server_for_daemon(root_path, ws_callback)
    runner = web.AppRunner(app)
    await runner.setup()

    path = socket_server_path(root_path)
    mkdir(path.parent)
    if path.exists():
        path.unlink()

    site, where = await create_site_for_daemon(runner, path, 55400)

    app["site"] = site
    lockfile.close()

    daemon_api.set_exit_callback(site.stop)

    print(f"daemon: listening on {where}", flush=True)
    task = asyncio.ensure_future(site._server.wait_closed())

    await task


def run_daemon(root_path):
    return asyncio.get_event_loop().run_until_complete(async_run_daemon(root_path))


def main():
    from src.util.default_root import DEFAULT_ROOT_PATH

    return run_daemon(DEFAULT_ROOT_PATH)


if __name__ == "__main__":
    main()
