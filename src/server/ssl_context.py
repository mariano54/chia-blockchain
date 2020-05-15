from pathlib import Path
import ssl
from typing import Optional, Dict

from src.server.outbound_message import NodeType
from src.util.config import config_path_for_filename


def loadSSLConfig(tipo: str, path: Path, config: Dict):
    if config is not None:
        try:
            return (
                config_path_for_filename(path, config[tipo]["crt"]),
                config_path_for_filename(path, config[tipo]["key"]),
            )
        except Exception:
            pass

    return None, None


def ssl_context_for_server(root_path: Path, config: Dict, local_type: NodeType) -> Optional[ssl.SSLContext]:
    ssl_context = ssl._create_unverified_context(purpose=ssl.Purpose.CLIENT_AUTH)
    private_cert, private_key = loadSSLConfig(
        "ssl", root_path, config
    )
    ssl_context.load_cert_chain(certfile=private_cert, keyfile=private_key)
    ssl_context.load_verify_locations(private_cert)

    if (
        local_type == NodeType.FULL_NODE
        or local_type == NodeType.INTRODUCER
    ):
        ssl_context.verify_mode = ssl.CERT_NONE
    else:
        ssl_context.verify_mode = ssl.CERT_REQUIRED
    return ssl_context


def ssl_context_for_client(root_path: Path, config: Dict, auth: bool) -> Optional[ssl.SSLContext]:
    ssl_context = ssl._create_unverified_context(purpose=ssl.Purpose.SERVER_AUTH)
    private_cert, private_key = loadSSLConfig(
        "ssl", root_path, config
    )

    ssl_context.load_cert_chain(certfile=private_cert, keyfile=private_key)
    if not auth:
        ssl_context.verify_mode = ssl.CERT_NONE
    else:
        ssl_context.verify_mode = ssl.CERT_REQUIRED
        ssl_context.load_verify_locations(private_cert)
    return ssl_context
