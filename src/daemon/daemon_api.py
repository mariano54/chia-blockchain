import asyncio
import logging
import os
import subprocess
import sys

from typing import Dict
from sys import platform

from src.util.path import mkdir
from src.util.service_groups import validate_service

log = logging.getLogger(__name__)

# determine if application is a script file or frozen exe
if getattr(sys, "frozen", False):
    name_map = {
        "chia": "chia",
        "chia-check-plots": "check_plots",
        "chia-create-plots": "create_plots",
        "chia-wallet": "wallet_server",
        "chia_full_node": "start_full_node",
        "chia_harvester": "start_harvester",
        "chia_farmer": "start_farmer",
        "chia_introducer": "start_introducer",
        "chia_timelord": "start_timelord",
        "chia_timelord_launcher": "timelord_launcher",
        "chia_full_node_simulator": "start_simulator",
        "plotter": "create_plots",
    }

    def executable_for_service(service_name):
        application_path = os.path.dirname(sys.executable)
        if platform == "win32" or platform == "cygwin":
            executable = name_map[service_name]
            path = f"{application_path}/{executable}.exe"
            return path
        else:
            path = f"{application_path}/{name_map[service_name]}"
            return path


else:
    application_path = os.path.dirname(__file__)

    def executable_for_service(service_name):
        return service_name


class DaemonAPI:
    def __init__(self, root_path):
        self.root_path = root_path
        self.log = log
        self.services: Dict = dict()

    def set_exit_callback(self, exit_callback):
        self.exit_callback = exit_callback

    async def ping(self, nonce: int = 0) -> str:
        return f"pong:{nonce}"

    async def start_service(self, service_name: str) -> str:
        if not validate_service(service_name):
            return "unknown service"

        if service_name in self.services:
            service = self.services[service_name]
            r = service is not None and service.poll() is None
            if r is False:
                self.services.pop(service_name)
            else:
                return "already running"

        try:
            process, pid_path = launch_service(self.root_path, service_name)
            self.services[service_name] = process
        except (subprocess.SubprocessError, IOError):
            log.exception(f"problem starting {service_name}")

        return "started"

    async def stop_service(self, service_name: str) -> bool:
        return await kill_service(self.root_path, self.services, service_name)

    async def is_running(self, service_name: str) -> bool:
        process = self.services.get(service_name)
        r = process is not None and process.poll() is None
        return r

    async def plotter_log_path(self) -> str:
        return plotter_log_path(self.root_path).absolute()

    async def exit(self) -> str:

        jobs = []
        for k in self.services.keys():
            jobs.append(kill_service(self.root_path, self.services, k))
        if jobs:
            await asyncio.wait(jobs)
        self.services.clear()

        self._exit_task = asyncio.ensure_future(self.exit_callback())
        return "stopped"


def plotter_log_path(root_path):
    return root_path / "plotter" / "plotter_log.txt"


def launch_service(root_path, service_command):
    """
    Launch a child process.
    """
    # set up CHIA_ROOT
    # invoke correct script
    # save away PID

    # we need to pass on the possibly altered CHIA_ROOT
    os.environ["CHIA_ROOT"] = str(root_path)

    # Insert proper executable
    service_array = service_command.split()
    service_name = service_array[0]
    service_executable = executable_for_service(service_name)
    service_array[0] = service_executable
    startupinfo = None
    if hasattr(subprocess, "STARTUPINFO"):
        startupinfo = subprocess.STARTUPINFO()  # type: ignore
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW  # type: ignore
    if service_name == "chia-create-plots":
        plotter_path = plotter_log_path(root_path)
        if plotter_path.parent.exists():
            if plotter_path.exists():
                plotter_path.unlink()
        else:
            mkdir(plotter_path.parent)
        outfile = open(plotter_path.resolve(), "w")
        process = subprocess.Popen(
            service_array, shell=False, stdout=outfile, startupinfo=startupinfo
        )
    else:
        process = subprocess.Popen(service_array, shell=False, startupinfo=startupinfo)
    pid_path = pid_path_for_service(root_path, service_command)
    try:
        mkdir(pid_path.parent)
        with open(pid_path, "w") as f:
            f.write(f"{process.pid}\n")
    except Exception:
        pass
    return process, pid_path


async def kill_service(root_path, services, service_name, delay_before_kill=15) -> bool:
    process = services.get(service_name)
    if process is None:
        return False
    del services[service_name]
    pid_path = pid_path_for_service(root_path, service_name)

    log.info("sending term signal to %s", service_name)
    process.terminate()
    # on Windows, process.kill and process.terminate are the same,
    # so no point in trying process.kill later
    if process.kill != process.terminate:
        count = 0
        while count < delay_before_kill:
            if process.poll() is not None:
                break
            await asyncio.sleep(1)
            count += 1
        else:
            process.kill()
            log.info("sending kill signal to %s", service_name)
    r = process.wait()
    log.info("process %s returned %d", service_name, r)
    try:
        pid_path_killed = pid_path.with_suffix(".pid-killed")
        if pid_path_killed.exists():
            pid_path_killed.unlink()
        os.rename(pid_path, pid_path_killed)
    except Exception:
        pass

    return True


def pid_path_for_service(root_path, service):
    """
    Generate a path for a PID file for the given service name.
    """
    pid_name = service.replace(" ", "-").replace("/", "-")
    return root_path / "run" / f"{pid_name}.pid"
