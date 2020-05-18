import asyncio
import logging
import logging.config
import signal

try:
    import uvloop
except ImportError:
    uvloop = None

from src.server.server import ChiaServer
from src.server.connection import NodeType
from src.util.logging import initialize_logging
from src.util.config import load_config_cli, load_config
from src.util.default_root import DEFAULT_ROOT_PATH
from src.util.setproctitle import setproctitle


async def async_start_service(
    api,
    service_type,
    root_path=DEFAULT_ROOT_PATH,
    signal_callback=None,
    service_name=None,
):
    if service_name is None:
        service_name = service_type
    net_config = load_config(root_path, "config.yaml")
    ping_interval = net_config.get("ping_interval")
    network_id = net_config.get("network_id")
    assert ping_interval is not None
    assert network_id is not None

    node_type = getattr(NodeType, service_name.upper())

    proctitle_name = f"chia_{service_name}"
    setproctitle(proctitle_name)
    log = logging.getLogger(service_name)

    config = load_config_cli(root_path, "config.yaml", service_name)
    initialize_logging("FullNode %(name)-23s", config["logging"], root_path)

    server = ChiaServer(
        config["port"],
        api,
        node_type,
        ping_interval,
        network_id,
        root_path,
        config,
    )
    if hasattr(api, "_set_server"):
        api._set_server(server)

    _ = await server.start_server(getattr(api, "_on_connect", None))

    server_closed = False

    def stop_server():
        nonlocal server_closed
        if not server_closed:
            server_closed = True
            server.close_all()
            if signal_callback:
                signal_callback()

    try:
        asyncio.get_running_loop().add_signal_handler(signal.SIGINT, stop_server)
        asyncio.get_running_loop().add_signal_handler(signal.SIGTERM, stop_server)
    except NotImplementedError:
        log.info("signal handlers unsupported")

    f = getattr(api, "_start_bg_tasks", None)
    if f:
        f()

    # Awaits for server and all connections to close
    await server.await_closed()
    log.info("Closed all node servers.")

    # Stops the api
    if hasattr(api, "stop"):
        await api.stop()

    log.info("Fully closed.")


def start_service(*args, **kwargs):
    if uvloop is not None:
        uvloop.install()
    asyncio.run(async_start_service(*args, **kwargs))
