"""Classes for application lifecycle."""

# Copyright (C) 2015  Jonathan David Page
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.


import asyncio
import configparser
import logging
import signal
import sys
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
        loop.run_until_complete(self.mc_server.start(loop))
        loop.create_task(self.http_server.start(loop))

        def stop(signame):
            def handler():
                _logger.info('received signal %s', signame)
                # relay signal to minecraft process
                if self.mc_server.process:
                    self.mc_server.process.send_signal(getattr(signal, signame))
                loop.stop()
            return handler

        for signame in ['SIGINT', 'SIGTERM']:
            loop.add_signal_handler(getattr(signal, signame), stop(signame))

        try:
            loop.run_forever()
        finally:
            loop.run_until_complete(self.mc_server.wait())
            loop.run_until_complete(self.http_server.stop())
            loop.close()
