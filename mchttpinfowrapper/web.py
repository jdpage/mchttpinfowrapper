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
    def handle_players(self, _):
        return web.Response(
            body=json.dumps(self._mc_server.players).encode('utf-8'))

    @asyncio.coroutine
    def handle_stop(self, request):
        auth_request = yield from self.require_authentication(request)
        if auth_request:
            return auth_request
        yield from self._mc_server.stop()
        return web.Response()

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
    def start(self, loop):
        app = web.Application(loop=loop)
        app.router.add_route('GET', '/players', self.handle_players)
        app.router.add_route('POST', '/server/stop', self.handle_stop)
        self._http_server = yield from loop.create_server(
            app.make_handler(),
            self._host, self._port)

    @asyncio.coroutine
    def stop(self):
        self._http_server.close()
        yield from self._http_server.wait_closed()

