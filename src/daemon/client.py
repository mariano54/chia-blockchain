from src.remote.client import connect_to_object_server

from src.util.path import mkdir

from .daemon_api import DaemonAPI


def should_use_unix_socket():
    """
    Use unix sockets unless they are not supported. Check `socket` to see.
    """
    import socket

    return 0
    return hasattr(socket, "AF_UNIX")


def socket_server_path(root_path):
    """
    This is the file that's either the unix socket or a text file containing
    the TCP socket information (ie. the port).
    """
    return root_path / "run" / "start-daemon.socket"


def uri_info_for_start_daemon(root_path, use_unix_socket):
    """
    Return the URI prefix and the path to the socket file.
    """
    path = socket_server_path(root_path)
    mkdir(path.parent)
    try:
        if use_unix_socket:
            return f"ws://unix", str(path)
        with open(path) as f:
            port = int(f.readline())
        return f"ws://127.0.0.1:{port}/ws/", None
    except Exception:
        pass

    return None


async def connect_to_daemon(root_path, use_unix_socket):
    """
    Connect to the local daemon.
    """
    url, unix_socket_path = uri_info_for_start_daemon(
        root_path, use_unix_socket
    )
    rpc_stream = await connect_to_object_server(url)

    daemon_api = rpc_stream.remote_obj(DaemonAPI, 0)

    rpc_stream.start()

    return daemon_api


async def connect_to_daemon_and_validate(root_path):
    """
    Connect to the local daemon and do a ping to ensure that something is really
    there and running.
    """
    try:
        connection = await connect_to_daemon(root_path, should_use_unix_socket())
        r = await connection.ping()

        if r.startswith("pong"):
            return connection
    except Exception as ex:
        # ConnectionRefusedError means that daemon is not yet running
        if not isinstance(ex, ConnectionRefusedError):
            print("Exception connecting to daemon: {ex}")
        return None
