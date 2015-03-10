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
        self._loop = None

    @staticmethod
    def make_token():
        return bytes(random.randint(0, 255) for _ in range(32))

    @staticmethod
    def make_body(data):
        return json.dumps(data, sort_keys=True, indent=4,
                          separators=(',', ': ')).encode('utf-8')

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
    def method_not_allowed(self, allowed, body=None):
        return web.Response(
            status=405,
            body=body,
            headers={
                'Allow': ", ".join(allowed)
            }
        )

    @asyncio.coroutine
    def handle_root(self, _):
        return web.Response(
            body=self.make_body({
                'endpoints': {
                    'players': {
                        'method': 'GET',
                        'href': '/players',
                    },
                    'server': {
                        'method': 'GET',
                        'href': '/server',
                    },
                }
            })
        )

    @asyncio.coroutine
    def handle_server(self, _):
        actions = {}
        if self._mc_server.can_start():
            actions['start_server'] = {
                'method': 'POST',
                'href': '/server/start',
            }
        if self._mc_server.can_stop():
            actions['stop_server'] = {
                'method': 'POST',
                'href': '/server/stop',
            }
        return web.Response(
            body=self.make_body({
                'stats': {
                    'status_changed_at':
                        self._mc_server.status_changed_at().isoformat(),
                    'status': self._mc_server.status(),
                },
                'endpoints': actions,
            })
        )

    @asyncio.coroutine
    def handle_players(self, _):
        player_info = dict()
        for player in self._mc_server.players():
            player_info[player] = {
                'joined_at': self._mc_server.joined_at(player).isoformat()
            }
        last_part = self._mc_server.last_part_at()
        return web.Response(
            body=self.make_body({
                'last_part_at': last_part and last_part.isoformat(),
                'players': player_info,
            })
        )

    @asyncio.coroutine
    def handle_server_start(self, request):
        auth_request = yield from self.require_authentication(request)
        if auth_request:
            return auth_request
        if not self._mc_server.can_start():
            return (
                yield from self.method_not_allowed(
                    allowed=[],
                    body=self.make_body({
                        'server_status': self._mc_server.status(),
                    })
                )
            )
        yield from self._mc_server.start(self._loop)
        return web.Response()

    @asyncio.coroutine
    def handle_server_stop(self, request):
        auth_request = yield from self.require_authentication(request)
        if auth_request:
            return auth_request
        if not self._mc_server.can_stop():
            return (
                yield from self.method_not_allowed(
                    allowed=[],
                    body=self.make_body({
                        'server_status': self._mc_server.status()
                    })
                )
            )
        yield from self._mc_server.stop()
        return web.Response()

    @asyncio.coroutine
    def start(self, loop):
        app = web.Application(loop=loop)
        app.router.add_route('GET', '/', self.handle_root)
        app.router.add_route('GET', '/players', self.handle_players)
        app.router.add_route('GET', '/server', self.handle_server)
        app.router.add_route('POST', '/server/start', self.handle_server_start)
        app.router.add_route('POST', '/server/stop', self.handle_server_stop)
        self._http_server = yield from loop.create_server(
            app.make_handler(),
            self._host, self._port)
        self._loop = loop

    @asyncio.coroutine
    def stop(self):
        self._http_server.close()
        yield from self._http_server.wait_closed()

