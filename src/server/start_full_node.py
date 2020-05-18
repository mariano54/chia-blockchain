import asyncio
import logging

try:
    import uvloop
except ImportError:
    uvloop = None

from src.full_node.full_node import FullNode
from src.rpc.rpc_server import start_rpc_server
from src.util.config import load_config_cli
from src.util.default_root import DEFAULT_ROOT_PATH

from .start_service import async_start_service


log = logging.getLogger(__name__)


async def async_main():
    service_type = "full_node"
    root_path = DEFAULT_ROOT_PATH
    config = load_config_cli(root_path, "config.yaml", service_type)

    api = await FullNode.create(config, root_path=root_path)

    def master_close_cb():
        # Called by the UI, when node is closed, or when a signal is sent
        log.info("Closing all connections, and server...")
        api._close()

    if config["start_rpc_server"]:
        # Starts the RPC server
        rpc_cleanup = await start_rpc_server(
            api, master_close_cb, config["rpc_port"]
        )

    await async_start_service(
        api,
        service_type,
        signal_callback=master_close_cb,
    )

    # Waits for the rpc server to close
    if rpc_cleanup is not None:
        await rpc_cleanup()


def main():
    if uvloop is not None:
        uvloop.install()
    asyncio.run(async_main())


if __name__ == "__main__":
    main()
