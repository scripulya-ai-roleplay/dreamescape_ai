from typing import Dict
from src.application.ports import ILLMChatGateway, IGatewayFactory


class GatewayFactory(IGatewayFactory):
	def __init__(self, gateways: Dict[str, ILLMChatGateway]):
		self._gateways = gateways

	def create_gateway(self, gateway_type: str) -> ILLMChatGateway:
		if gateway_type not in self._gateways:
			raise ValueError(f"Unknown gateway type: {gateway_type}")
		return self._gateways[gateway_type]
