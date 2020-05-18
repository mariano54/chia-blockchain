import asyncio
import logging

try:
    import uvloop
except ImportError:
    uvloop = None

from src.full_node.full_node import FullNode
from src.rpc.rpc_server import start_rpc_server
from src.server.connection import NodeType
from src.util.config import load_config_cli
from src.util.default_root import DEFAULT_ROOT_PATH

from .start_service import async_start_service


log = logging.getLogger(__name__)


async def async_main():
    root_path = DEFAULT_ROOT_PATH
    config = load_config_cli(root_path, "config.yaml", "full_node")

    full_node = await FullNode.create(config, root_path=root_path)

    def master_close_cb():
        # Called by the UI, when node is closed, or when a signal is sent
        log.info("Closing all connections, and server...")
        full_node._close()

    if config["start_rpc_server"]:
        # Starts the RPC server
        rpc_cleanup = await start_rpc_server(
            full_node, master_close_cb, config["rpc_port"]
        )

    full_node = await FullNode.create(config, root_path=root_path)
    await async_start_service(
        DEFAULT_ROOT_PATH,
        "chia_full_node",
        "full_node",
        full_node,
        NodeType.FULL_NODE,
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
