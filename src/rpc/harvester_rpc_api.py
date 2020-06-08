from typing import Dict, Optional
from blspy import PrivateKey, PublicKey

from src.harvester import Harvester
from src.util.ws_message import create_payload


class HarvesterRpcApi:
    def __init__(self, harvester: Harvester):
        self._harvester = harvester

    async def _state_changed(self, change: str):
        assert self.websocket is not None

        if change == "plots":
            data = await self.get_plots({})
            payload = create_payload("get_plots", data, self.service_name, "wallet_ui")
        else:
            await super()._state_changed(change)
            return
        try:
            await self.websocket.send_str(payload)
        except (BaseException) as e:
            try:
                self.log.warning(f"Sending data failed. Exception {type(e)}.")
            except BrokenPipeError:
                pass

    async def get_plots(self) -> Dict:
        plots, failed_to_open, not_found = self.service._get_plots()
        return {
            "plots": plots,
            "failed_to_open_filenames": failed_to_open,
            "not_found_filenames": not_found,
        }

    async def refresh_plots(self) -> None:
        self.service._refresh_plots()

    async def delete_plot(self, filename: str) -> bool:
        return self.service._delete_plot(filename)

    async def add_plot(self, filename: str, pool_pk: Optional[PublicKey], plot_sk: PrivateKey) -> bool:
        success = self.service._add_plot(filename, plot_sk, pool_pk)
        return success
