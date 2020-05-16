import asyncio
import logging
import ssl
from secrets import token_bytes
from typing import Any, AsyncGenerator, List, Optional, Tuple

from aiter import iter_to_aiter, map_aiter, push_aiter
from aiter.server import start_server_aiter

from src.protocols.shared_protocol import (
    Ping,
)
from src.server.connection import OnConnectFunc, PeerConnections
from src.server.outbound_message import Delivery, Message, NodeType, OutboundMessage
from src.types.peer_info import PeerInfo
from src.types.sized_bytes import bytes32
from src.util.network import create_node_id

from .pipeline import run_pipeline


class ChiaServer:
    def __init__(
        self,
        port: int,
        api: Any,
        local_type: NodeType,
        ping_interval: int,
        network_id: str,
        ssl_context_client: Optional[ssl.SSLContext] = None,
        ssl_context_server: Optional[ssl.SSLContext] = None,
        name: str = None,
    ):
        # Keeps track of all connections to and from this node.
        self.global_connections: PeerConnections = PeerConnections([])

        # Optional listening server. You can also use this class without starting one.
        self._server: Optional[asyncio.AbstractServer] = None

        # Called for inbound connections after successful handshake
        self._on_inbound_connect: OnConnectFunc = None

        self._port = port  # TCP port to identify our node
        self._api = api  # API module that will be called from the requests
        self._local_type = local_type  # NodeType (farmer, full node, timelord, pool, harvester, wallet)

        self._ping_interval = ping_interval
        self._network_id = network_id
        # (StreamReader, StreamWriter, NodeType) aiter, gets things from server and clients and
        # sends them through the pipeline
        self._srwt_aiter: push_aiter = push_aiter()

        # Aiter used to broadcase messages
        self._outbound_aiter: push_aiter = push_aiter()

        # Our unique random node id that we will other peers, regenerated on launch
        self._node_id = create_node_id()

        # Tasks for entire server pipeline
        self._pipeline_task: asyncio.Future = asyncio.ensure_future(
            run_pipeline(
                self._srwt_aiter,
                self._api,
                self._port,
                self._network_id,
                self._node_id,
                self._local_type,
                self._srwt_aiter,
                self._outbound_aiter,
                self._on_inbound_connect,
                self.global_connections,
            )
        )

        self._ssl_context_client = ssl_context_client
        self._ssl_context_server = ssl_context_server

        # Taks list to keep references to tasks, so they don'y get GCd
        self._tasks: List[asyncio.Task] = [self._initialize_ping_task()]
        if name:
            self.log = logging.getLogger(name)
        else:
            self.log = logging.getLogger(__name__)

    async def start_server(self, on_connect: OnConnectFunc = None) -> bool:
        """
        Launches a listening server on host and port specified, to connect to NodeType nodes. On each
        connection, the on_connect asynchronous generator will be called, and responses will be sent.
        Whenever a new TCP connection is made, a new srwt tuple is sent through the pipeline.
        """
        if self._server is not None or self._pipeline_task.done():
            return False

        self._server, aiter = await start_server_aiter(
            self._port, host=None, reuse_address=True, ssl=self._ssl_context_server
        )

        if on_connect is not None:
            self._on_inbound_connect = on_connect

        def add_connection_type(
            srw: Tuple[asyncio.StreamReader, asyncio.StreamWriter]
        ) -> Tuple[asyncio.StreamReader, asyncio.StreamWriter, None]:
            ssl_object = srw[1].get_extra_info(name="ssl_object")
            peer_cert = ssl_object.getpeercert()
            self.log.info(f"Client authed as {peer_cert}")
            return (srw[0], srw[1], None)

        srwt_aiter = map_aiter(add_connection_type, aiter)

        # Push all aiters that come from the server, into the pipeline
        self._tasks.append(asyncio.create_task(self._add_to_srwt_aiter(srwt_aiter)))

        self.log.info(f"Server started on port {self._port}")
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
        if self._server is not None:
            if (
                target_node.host == "127.0.0.1"
                or target_node.host == "0.0.0.0"
                or target_node.host == "::1"
                or target_node.host == "0:0:0:0:0:0:0:1"
            ) and self._port == target_node.port:
                self.global_connections.peers.remove(target_node)
                return False
        if self._pipeline_task.done():
            return False

        try:
            reader, writer = await asyncio.open_connection(
                target_node.host, int(target_node.port), ssl=self._ssl_context_client
            )
        except (
            ConnectionRefusedError,
            TimeoutError,
            OSError,
            asyncio.TimeoutError,
        ) as e:
            self.log.warning(
                f"Could not connect to {target_node}. {type(e)}{str(e)}. Aborting and removing peer."
            )
            self.global_connections.peers.remove(target_node)
            return False
        self._tasks.append(
            asyncio.create_task(
                self._add_to_srwt_aiter(iter_to_aiter([(reader, writer, on_connect)]))
            )
        )

        ssl_object = writer.get_extra_info(name="ssl_object")
        peer_cert = ssl_object.getpeercert()
        self.log.info(f"Server authed as {peer_cert}")

        return True

    async def _add_to_srwt_aiter(
        self,
        aiter: AsyncGenerator[
            Tuple[asyncio.StreamReader, asyncio.StreamWriter, OnConnectFunc], None
        ],
    ):
        """
        Adds all swrt from aiter into the instance variable srwt_aiter, adding them to the pipeline.
        """
        async for swrt in aiter:
            if not self._srwt_aiter.is_stopped():
                self._srwt_aiter.push(swrt)

    async def await_closed(self):
        """
        Await until the pipeline is done, after which the server and all clients are closed.
        """
        await self._pipeline_task

    def push_message(self, message: OutboundMessage):
        """
        Sends a message into the middle of the pipeline, to be sent to peers.
        """
        if not self._outbound_aiter.is_stopped():
            self._outbound_aiter.push(message)

    def close_all(self):
        """
        Starts closing all the clients and servers, by stopping the server and stopping the aiters.
        """
        self.global_connections.close_all_connections()
        if self._server is not None:
            self._server.close()
        if not self._outbound_aiter.is_stopped():
            self._outbound_aiter.stop()
        if not self._srwt_aiter.is_stopped():
            self._srwt_aiter.stop()

    def _initialize_ping_task(self):
        async def ping():
            while not self._pipeline_task.done():
                msg = Message("ping", Ping(bytes32(token_bytes(32))))
                self.push_message(
                    OutboundMessage(NodeType.FARMER, msg, Delivery.BROADCAST)
                )
                self.push_message(
                    OutboundMessage(NodeType.TIMELORD, msg, Delivery.BROADCAST)
                )
                self.push_message(
                    OutboundMessage(NodeType.FULL_NODE, msg, Delivery.BROADCAST)
                )
                self.push_message(
                    OutboundMessage(NodeType.HARVESTER, msg, Delivery.BROADCAST)
                )
                self.push_message(
                    OutboundMessage(NodeType.WALLET, msg, Delivery.BROADCAST)
                )
                await asyncio.sleep(self._ping_interval)

        return asyncio.create_task(ping())
