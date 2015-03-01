import asyncio
import configparser
import logging
from . import minecraft, web

_logger = logging.getLogger(__name__)


class Application:
    def __init__(self, config_file='config.ini'):
        _logger.info("Parsing config")
        self.config = configparser.ConfigParser()
        self.config.read(config_file)
        self.mc_server = minecraft.ServerWrapper(self.config['minecraft'])
        self.http_server = web.Server(self.config['http'], self.mc_server)

    def run(self):
        _logger.info("Starting application")
        loop = asyncio.get_event_loop()

        loop.run_until_complete(self.mc_server.start())
        self.mc_server.handle_io(loop)
        loop.create_task(self.http_server.start(loop))
        loop.run_until_complete(self.mc_server.wait())
        loop.run_until_complete(self.http_server.stop())
