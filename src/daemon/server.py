import asyncio
import logging

from src.cmds.init import chia_init

from src.util.config import load_config
from src.util.logging import initialize_logging
from src.util.path import mkdir

from src.remote.server import create_object_server, create_tcp_site, create_unix_site

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


async def async_run_daemon(root_path):
    chia_init(root_path)
    config = load_config(root_path, "config.yaml")
    initialize_logging("daemon %(name)-25s", config["logging"], root_path)

    connection = await connect_to_daemon_and_validate(root_path)
    if connection is not None:
        print("daemon: already running")
        return 1

    daemon_api = DaemonAPI(root_path)

    lockfile = singleton(daemon_launch_lock_path(root_path))
    if lockfile is None:
        print("daemon: already launching")
        return 2

    path = socket_server_path(root_path)
    mkdir(path.parent)
    if path.exists():
        path.unlink()

    use_unix_socket = should_use_unix_socket() and 0

    async def create_site_for_daemon(runner):
        if use_unix_socket:
            return await create_unix_site(runner, path)

        return await create_tcp_site(runner, 55400)

    site, where = await create_object_server(daemon_api, "/ws/", create_site_for_daemon)

    if not use_unix_socket:
        with open(path, "w") as f:
            f.write(f"{where}\n")

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
