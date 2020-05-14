import asyncio
import logging
import random

from pathlib import Path
from typing import Any, AsyncGenerator, List, Optional, Tuple, Dict, Union

import aiohttp.web

from src.protocols.shared_protocol import (
    Handshake,
    HandshakeAck,
    Ping,
    Pong,
    protocol_version,
)
from src.server.connection import Connection, OnConnectFunc, PeerConnections
from src.server.outbound_message import Delivery, Message, NodeType, OutboundMessage
from src.types.peer_info import PeerInfo
from src.util.errors import Err, ProtocolError
from src.util.ints import uint16
from src.util.network import create_node_id


class ChiaServer:
    def __init__(
        self,
        port: int,
        api: Any,
        local_type: NodeType,
        ping_interval: int,
        network_id: str,
        root_path: Path,
        config: Dict,
        name: str = None,
    ):
        self._port = port
        self._api = api
        self._local_type = local_type
        self._ping_interval = ping_interval
        self._network_id = network_id
        self._root_path = root_path
        self._config = config
        self._name = name
        self._site: Optional[aiohttp.web.TCPSite] = None

        # Our unique random node id that we will other peers, regenerated on launch
        self._node_id = create_node_id()

        if name:
            self.log = logging.getLogger(name)
        else:
            self.log = logging.getLogger(__name__)
        self.global_connections: PeerConnections = PeerConnections([])

    async def _async_close_all(self):
        """
        Starts closing all the clients and servers, by stopping the server and stopping the aiters.
        """
        if self._site:
            await self._site.stop()
        for _ in self._all_connections:
            _.close()

    def close_all(self):
        self._close_task = asyncio.ensure_future(self._async_close_all())

    async def start_server(self, on_connect: OnConnectFunc = None) -> bool:
        """
        Launches a listening server on host and port specified, to connect to NodeType nodes. On each
        connection, the on_connect asynchronous generator will be called, and responses will be sent.
        """
        routes = aiohttp.web.RouteTableDef()

        @routes.get("/")
        async def new_connection(request):
            ws = aiohttp.web.WebSocketResponse()
            await ws.prepare(request)
            await self.do_connection(ws, on_connect)
            return ws

        app = aiohttp.web.Application()
        app.add_routes(routes)
        runner = aiohttp.web.AppRunner(app)

        await runner.setup()

        host = "127.0.0.1"
        self._site = aiohttp.web.TCPSite(runner, host, self._port)

        await self._site.start()
        return True

    async def start_client(
        self,
        target_node: PeerInfo,
        on_connect: OnConnectFunc = None,
        auth: bool = False,
    ) -> bool:
        """
        Tries to connect to the target node, adding one connection into the pipeline, if successful.
        An on connect method can also be specified, and this will be saved into the instance variables.
        """
        async with aiohttp.ClientSession() as session:
            async with session.ws_connect(
                f"http://{target_node.host}:{target_node.port}/"
            ) as ws:
                breakpoint()
                await self.do_connection(ws, on_connect)
        return True

    async def await_closed(self):
        await self._site._server.wait_closed()

    async def handle_message(
        self, pair: Tuple[Connection, Message], api: Any
    ) -> AsyncGenerator[Tuple[Connection, OutboundMessage], None]:
        """
        Async generator which takes messages, parses, them, executes the right
        api function, and yields responses (to same connection, propagated, etc).
        """
        connection, full_message = pair
        try:
            if len(full_message.function) == 0 or full_message.function.startswith("_"):
                # This prevents remote calling of private methods that start with "_"
                raise ProtocolError(
                    Err.INVALID_PROTOCOL_MESSAGE, [full_message.function]
                )

            self.log.info(
                f"<- {full_message.function} from peer {connection.get_peername()}"
            )
            if full_message.function == "ping":
                ping_msg = Ping(full_message.data["nonce"])
                assert connection.connection_type
                yield connection, OutboundMessage(
                    connection.connection_type,
                    Message("pong", Pong(ping_msg.nonce)),
                    Delivery.RESPOND,
                )
                return
            elif full_message.function == "pong":
                return

            f_with_peer_name = getattr(
                api, full_message.function + "_with_peer_name", None
            )

            if f_with_peer_name is not None:
                result = f_with_peer_name(full_message.data, connection.get_peername())
            else:
                f = getattr(api, full_message.function, None)

                if f is None:
                    raise ProtocolError(
                        Err.INVALID_PROTOCOL_MESSAGE, [full_message.function]
                    )

                result = f(full_message.data)

            if isinstance(result, AsyncGenerator):
                async for outbound_message in result:
                    yield connection, outbound_message
            else:
                await result
        except Exception:
            self.log.exception(f"Error, closing connection {connection}")
            # TODO: Exception means peer gave us invalid information, so ban this peer.
            self.global_connections.close(connection)

    async def expand_outbound_messages(
        self, pair: Tuple[Connection, OutboundMessage]
    ) -> AsyncGenerator[Tuple[Connection, Optional[Message]], None]:
        """
        Expands each of the outbound messages into it's own message.
        """
        connection, outbound_message = pair

        if connection and outbound_message.delivery_method == Delivery.RESPOND:
            if connection.connection_type == outbound_message.peer_type:
                # Only select this peer, and only if it's the right type
                yield connection, outbound_message.message
        elif outbound_message.delivery_method == Delivery.RANDOM:
            # Select a random peer.
            to_yield_single: Tuple[Connection, Message]
            typed_peers: List[Connection] = [
                peer
                for peer in self.global_connections.get_connections()
                if peer.connection_type == outbound_message.peer_type
            ]
            if len(typed_peers) == 0:
                return
            yield (random.choice(typed_peers), outbound_message.message)
        elif (
            outbound_message.delivery_method == Delivery.BROADCAST
            or outbound_message.delivery_method == Delivery.BROADCAST_TO_OTHERS
        ):
            # Broadcast to all peers.
            for peer in self.global_connections.get_connections():
                if peer.connection_type == outbound_message.peer_type:
                    if peer == connection:
                        if outbound_message.delivery_method == Delivery.BROADCAST:
                            yield (peer, outbound_message.message)
                    else:
                        yield (peer, outbound_message.message)
        elif outbound_message.delivery_method == Delivery.CLOSE:
            # Close the connection but don't ban the peer
            yield (connection, None)

    async def process_message(self, con, msg):
        async for out_con, out_msg in self.handle_message(
            (con, msg), self._api
        ):
            async for connection, message in self.expand_outbound_messages(
                (out_con, out_msg)
            ):
                if message is None:
                    # Does not ban the peer, this is just a graceful close of connection.
                    self.global_connections.close(connection, True)
                    continue
                self.log.info(
                    f"-> {message.function} to peer {connection.get_peername()}"
                )
                try:
                    await connection.send(message)
                except (RuntimeError, TimeoutError, OSError,) as e:
                    self.log.warning(
                        f"Cannot write to {connection}, already closed. Error {e}."
                    )
                    self.global_connections.close(connection, True)

    async def do_connection(
        self,
        ws: Union[aiohttp.ClientWebSocketResponse, aiohttp.web.WebSocketResponse],
        on_connect: OnConnectFunc,
    ):
        con = Connection(self._local_type, None, ws, self._port, on_connect)

        try:
            # Send handshake message
            outbound_handshake = Message(
                "handshake",
                Handshake(
                    self._network_id,
                    protocol_version,
                    self._node_id,
                    uint16(self._port),
                    self._local_type,
                ),
            )
            await con.send(outbound_handshake)

            # Read handshake message
            full_message = await con.read_one_message()
            inbound_handshake = Handshake(**full_message.data)
            if (
                full_message.function != "handshake"
                or not inbound_handshake
                or not inbound_handshake.node_type
            ):
                raise ProtocolError(Err.INVALID_HANDSHAKE)

            if inbound_handshake.node_id == self._node_id:
                raise ProtocolError(Err.SELF_CONNECTION)

            # Makes sure that we only start one connection with each peer
            con.node_id = inbound_handshake.node_id
            con.peer_server_port = int(inbound_handshake.server_port)
            con.connection_type = inbound_handshake.node_type
            if not self.global_connections.add(con):
                raise ProtocolError(Err.DUPLICATE_CONNECTION, [False])

            # Send Ack message
            await con.send(Message("handshake_ack", HandshakeAck()))

            # Read Ack message
            full_message = await con.read_one_message()
            if full_message.function != "handshake_ack":
                raise ProtocolError(Err.INVALID_ACK)

            if inbound_handshake.version != protocol_version:
                raise ProtocolError(
                    Err.INCOMPATIBLE_PROTOCOL_VERSION,
                    [protocol_version, inbound_handshake.version],
                )

            self.log.info(
                (
                    f"Handshake with {NodeType(con.connection_type).name} {con.get_peername()} "
                    f"{con.node_id}"
                    f" established"
                )
            )

            # do on_connect messages

            for func in con.on_connect, on_connect:
                if func:
                    async for obm in func():
                        async for connection, message in self.expand_outbound_messages(
                            (con, obm)
                        ):
                            if message is not None:
                                await connection.send(message)

            while True:
                msg = await con.read_one_message()
                self.process_message(con, msg)
        except Exception as ex:
            print(ex)
            breakpoint()
            print(ex)
