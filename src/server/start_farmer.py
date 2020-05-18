import asyncio

try:
    import uvloop
except ImportError:
    uvloop = None

from src.cmds.init import check_keys
from src.farmer import Farmer
from src.util.config import load_config_cli, load_config
from src.util.default_root import DEFAULT_ROOT_PATH

from .start_service import async_start_service


async def async_main():
    service_type = "farmer"
    root_path = DEFAULT_ROOT_PATH
    config = load_config_cli(root_path, "config.yaml", service_type)

    try:
        check_keys(root_path)
        key_config = load_config(root_path, "keys.yaml")
    except FileNotFoundError:
        raise RuntimeError("Keys not generated. Run `chia generate keys`")

    api = Farmer(config, key_config)

    await async_start_service(
        api,
        service_type,
        DEFAULT_ROOT_PATH,
    )


def main():
    if uvloop is not None:
        uvloop.install()
    asyncio.run(async_main())


if __name__ == "__main__":
    main()
