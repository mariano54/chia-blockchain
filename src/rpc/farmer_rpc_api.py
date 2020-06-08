from typing import Set, Dict

from src.farmer import Farmer
from src.util.ws_message import create_payload


class FarmerRpcApi:
    def __init__(self, farmer: Farmer):
        self._farmer = farmer

    async def _state_changed(self, change: str):
        assert self.websocket is not None

        if change == "challenge":
            data = await self.get_latest_challenges({})
            payload = create_payload(
                "get_latest_challenges", data, self.service_name, "wallet_ui"
            )
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

    async def get_latest_challenges(self) -> Dict:
        response = []
        seen_challenges: Set = set()
        if self.service.current_weight == 0:
            return {"success": True, "latest_challenges": []}
        for pospace_fin in self.service.challenges[self.service.current_weight]:
            estimates = self.service.challenge_to_estimates.get(
                pospace_fin.challenge_hash, []
            )
            if pospace_fin.challenge_hash in seen_challenges:
                continue
            response.append(
                {
                    "challenge": pospace_fin.challenge_hash,
                    "weight": pospace_fin.weight,
                    "height": pospace_fin.height,
                    "difficulty": pospace_fin.difficulty,
                    "estimates": estimates,
                }
            )
            seen_challenges.add(pospace_fin.challenge_hash)
        return response
