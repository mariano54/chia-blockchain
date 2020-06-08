import websockets

from src.remote.json_packaging import rpc_stream_for_websocket


class WebsocketRemote:
    def __init__(self, uri):
        self._uri = uri

    async def start(self):
        self._websocket = await websockets.connect(self._uri)

    async def __aiter__(self):
        while True:
            _ = await self._websocket.recv()
            yield _

    async def push(self, msg):
        await self._websocket.send(msg)


async def connect_to_object_server(url):
    """
    Connect to an object server.

    You must call rpc_stream.start() before using it (but after registering local and remote objects).
    """
    ws = WebsocketRemote(url)
    await ws.start()
    return rpc_stream_for_websocket(ws)
