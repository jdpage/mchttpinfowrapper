import asyncio
import configparser
import logging
from . import minecraft

_logger = logging.getLogger(__name__)


class Application:
    def __init__(self, config_file='config.ini'):
        _logger.info("Parsing config")
        self.config = configparser.ConfigParser()
        self.config.read(config_file)
        self.server = minecraft.ServerWrapper(self.config["minecraft"])

    def run(self):
        _logger.info("Starting application")
        loop = asyncio.get_event_loop()
        loop.run_until_complete(self.server.start())
        self.server.handle_io(loop)
        loop.run_until_complete(self.server.wait())

#         self.port = mc_config.get("Port", 80)
#         self.host = mc_config.get("Host", "0.0.0.0")
