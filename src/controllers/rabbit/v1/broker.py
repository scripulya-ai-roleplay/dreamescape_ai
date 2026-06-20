from faststream.rabbit import RabbitBroker

from src.conf import settings

# Module-level singleton broker, shared by:
#   - the llm.agent.result subscriber (controllers/rabbit/v1/llm.py), and
#   - the scripulya_agent client, which publishes llm.agent.request.
# It is connected on FastAPI startup and closed on shutdown (see src/app.py).
broker = RabbitBroker(settings.RABBIT_URL)
