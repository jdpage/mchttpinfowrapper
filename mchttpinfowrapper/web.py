"""Classes for HTTP control and information interface."""

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
from aiohttp import web
import json
import random
import base64
import logging

_logger = logging.getLogger(__name__)


class Server:
    def __init__(self, http_config, mc_server):
        self._host = http_config.get('Host', "0.0.0.0")
        self._port = int(http_config.get('Port', "80"))
        self._key = http_config.get('SecretKey', None)
        if self._key:
            self._key = b':' + self._key.encode('ascii')
        self._mc_server = mc_server
        self._http_server = None
        self._tokens = dict()

    @staticmethod
    def make_token():
        return bytes(random.randint(0, 255) for _ in range(32))

    @asyncio.coroutine
    def require_authentication(self, request):
        if not self._key:
            return web.Response(status=403)
        if 'Authorization' in request.headers:
            scheme, *auth = request.headers['Authorization'].split()
            if scheme == 'Basic':
                remote_auth = base64.b64decode(auth[0])
                if self._key == remote_auth:
                    return None
        return web.Response(
            status=401,
            headers={
                'WWW-Authenticate': 'Basic realm="mc admin"'
            }
        )

    @asyncio.coroutine
    def handle_root(self, _):
        return web.Response(
            body=json.dumps({
                'player_info': {
                    'method': 'GET',
                    'href': '/players',
                },
                'server_info': {
                    'method': 'GET',
                    'href': '/server',
                },
            }).encode('utf-8')
        )

    @asyncio.coroutine
    def handle_server(self, _):
        return web.Response(
            body=json.dumps({
                'stats': {
                    'uptime': str(self._mc_server.uptime()),
                },
                'shutdown_server': {
                    'method': 'POST',
                    'href': '/server/stop',
                },
            }).encode('utf-8')
        )

    @asyncio.coroutine
    def handle_players(self, _):
        player_info = dict()
        for player in self._mc_server.players():
            player_info[player] = {
                'play_time': str(self._mc_server.time_since_joined(player))
            }
        tslp = self._mc_server.time_since_last_part()
        return web.Response(
            body=json.dumps({
                'time_since_last_part': tslp and str(tslp),
                'players': player_info,
            }).encode('utf-8')
        )

    @asyncio.coroutine
    def handle_server_stop(self, request):
        auth_request = yield from self.require_authentication(request)
        if auth_request:
            return auth_request
        yield from self._mc_server.stop()
        return web.Response()

    @asyncio.coroutine
    def start(self, loop):
        app = web.Application(loop=loop)
        app.router.add_route('GET', '/', self.handle_root)
        app.router.add_route('GET', '/players', self.handle_players)
        app.router.add_route('GET', '/server', self.handle_server)
        app.router.add_route('POST', '/server/stop', self.handle_server_stop)
        self._http_server = yield from loop.create_server(
            app.make_handler(),
            self._host, self._port)

    @asyncio.coroutine
    def stop(self):
        self._http_server.close()
        yield from self._http_server.wait_closed()

