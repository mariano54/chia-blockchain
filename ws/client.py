import asyncio

import aiohttp


async def async_main():
    async with aiohttp.ClientSession() as session:
        port = 8444
        async with session.ws_connect(f'ws://127.0.0.1:{port}/') as ws:
            breakpoint()
            await ws.send_bytes(b"hiya")
            async for msg in ws:
                if msg.type == aiohttp.WSMsgType.TEXT:
                    if msg.data == 'close cmd':
                        await ws.close()
                        break
                    else:
                        await ws.send_str(msg.data + '/answer')
                elif msg.type == aiohttp.WSMsgType.ERROR:
                    break


async def async_main2():
    from src.full_node.full_node import FullNode
    from src.rpc.rpc_server import start_rpc_server
    from src.server.server import ChiaServer
    from src.server.connection import NodeType
    from src.util.logging import initialize_logging
    from src.util.config import load_config_cli, load_config
    from src.util.default_root import DEFAULT_ROOT_PATH
    from src.util.setproctitle import setproctitle
    from src.types.peer_info import PeerInfo
    import logging
    root_path = DEFAULT_ROOT_PATH
    config = load_config_cli(root_path, "config.yaml", "full_node")
    net_config = load_config(root_path, "config.yaml")
    setproctitle("chia_full_node")

    log = logging.getLogger(__name__)
    server_closed = False

    #full_node = await FullNode.create(config, root_path=root_path)

    ping_interval = 10
    network_id = b"foo"
    server = ChiaServer(
        10000,
        None,
        NodeType.FULL_NODE,
        ping_interval,
        network_id,
        DEFAULT_ROOT_PATH,
        config,
    )
    #full_node._set_server(server)
    target_node = PeerInfo("127.0.0.1", 8444)
    await server.start_client(target_node)


def main():
    asyncio.get_event_loop().run_until_complete(async_main())
    


async_main = async_main2


if __name__ == "__main__":
    main()
