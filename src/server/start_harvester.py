import asyncio

try:
    import uvloop
except ImportError:
    uvloop = None

from src.harvester import Harvester
from src.util.config import load_config, load_config_cli
from src.util.default_root import DEFAULT_ROOT_PATH

from .start_service import async_start_service


async def async_main():
    service_type = "harvester"
    root_path = DEFAULT_ROOT_PATH
    config = load_config_cli(root_path, "config.yaml", service_type)

    try:
        plot_config = load_config(root_path, "plots.yaml")
    except FileNotFoundError:
        raise RuntimeError("Plots not generated. Run chia-create-plots")

    api = await Harvester.create(config, plot_config)
    await async_start_service(
        api,
        service_type,
    )


def main():
    if uvloop is not None:
        uvloop.install()
    asyncio.run(async_main())


if __name__ == "__main__":
    main()
