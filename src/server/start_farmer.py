import asyncio
import signal
import logging

try:
    import uvloop
except ImportError:
    uvloop = None

from src.farmer import Farmer
from src.server.outbound_message import NodeType
from src.server.server import ChiaServer, start_server
from src.types.peer_info import PeerInfo
from src.util.config import load_config, load_config_cli
from src.util.default_root import DEFAULT_ROOT_PATH
from src.cmds.init import check_keys
from src.util.logging import initialize_logging
from src.util.setproctitle import setproctitle

from .reconnect_task import start_reconnect_task


async def async_main():
    root_path = DEFAULT_ROOT_PATH
    net_config = load_config(root_path, "config.yaml")
    config = load_config_cli(root_path, "config.yaml", "farmer")
    try:
        check_keys(root_path)
        key_config = load_config(root_path, "keys.yaml")
    except FileNotFoundError:
        raise RuntimeError("Keys not generated. Run `chia generate keys`")

    initialize_logging("Farmer %(name)-25s", config["logging"], root_path)
    log = logging.getLogger(__name__)
    setproctitle("chia_farmer")

    farmer = Farmer(config, key_config)

    ping_interval = net_config.get("ping_interval")
    network_id = net_config.get("network_id")
    assert ping_interval is not None
    assert network_id is not None
    server = ChiaServer(
        config["port"],
        farmer,
        NodeType.FARMER,
        ping_interval,
        network_id,
        root_path,
        config,
    )

    peer_info = PeerInfo(
        config["full_node_peer"]["host"], config["full_node_peer"]["port"]
    )

    server_socket = await start_server(server, farmer._on_connect)
    farmer_bg_task = start_reconnect_task(server, peer_info, log)

    def stop_all():
        server_socket.close()
        server.close_all()
        farmer_bg_task.cancel()

    try:
        asyncio.get_running_loop().add_signal_handler(signal.SIGINT, stop_all)
        asyncio.get_running_loop().add_signal_handler(signal.SIGTERM, stop_all)
    except NotImplementedError:
        log.info("signal handlers unsupported")

    await asyncio.sleep(10)  # Allows full node to startup

    await server_socket.wait_closed()
    await server.await_closed()

    log.info("Farmer fully closed.")


def main():
    if uvloop is not None:
        uvloop.install()
    asyncio.run(async_main())


if __name__ == "__main__":
    main()
