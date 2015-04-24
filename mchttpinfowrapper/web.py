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


from abc import ABCMeta, abstractmethod
import asyncio
from aiohttp import web
import functools
import simplejson as json
import random
import base64
import logging
from . import archive
from . import version as _version

_logger = logging.getLogger(__name__)


class RouteInfo:
    def __init__(self):
        self.routes = []

    def handle(self, method, url):
        def decorate(handler):
            self.routes.append((method, url, handler))
            return handler
        return decorate

    def handle_get(self, url):
        return self.handle('GET', url)

    def handle_post(self, url):
        return self.handle('POST', url)

    def register_all(self, instance, router):
        for method, url, handler in self.routes:
            router.add_route(method, url, functools.partial(handler, instance))


class Server:
    def __init__(self, http_config, mc_server):
        self._host = http_config.get('Host', None)
        self._port = int(http_config.get('Port', "80"))
        self._key = http_config.get('SecretKey', None)
        if self._key:
            self._key = b':' + self._key.encode('ascii')
        self._mc_server = mc_server
        self._http_server = None
        self._tokens = dict()
        self._loop = None

    route_info = RouteInfo()

    @staticmethod
    def make_token():
        return bytes(random.randint(0, 255) for _ in range(32))

    @staticmethod
    def make_response(request, status=200, headers=None, data=None):
        # format the data as JSON
        body = data and json.dumps(data, sort_keys=True, indent=4,
                                       separators=(',',': '))

        # get the JSONP callback, if any
        callback = None
        if request.method == 'GET' and 'callback' in request.GET:
            callback = request.GET['callback']
        elif request.method == 'POST' \
                and 'callback' in (yield from request.post()):
            callback = request.POST['callback']

        # if we're doing JSONP, wrap the data
        if callback:
            body = '{0}({1});'.format(callback, body or 'null')

        return web.Response(
            status=status,
            content_type=data or 'application/json',
            headers=headers,
            body=body and body.encode('utf-8'),
        )

    @asyncio.coroutine
    def require_authentication(self, request):
        if not self._key:
            return self.make_response(request, status=403)
        if 'Authorization' in request.headers:
            scheme, *auth = request.headers['Authorization'].split()
            if scheme == 'Basic':
                remote_auth = base64.b64decode(auth[0])
                if self._key == remote_auth:
                    return None
        return self.make_response(
            request,
            status=401,
            headers={
                'WWW-Authenticate': 'Basic realm="mc admin"'
            }
        )

    @asyncio.coroutine
    def method_not_allowed(self, request, allowed, data=None):
        return self.make_response(
            request,
            status=405,
            data=data,
            headers={'Allow': ", ".join(allowed)}
        )

    @route_info.handle_get('/')
    @asyncio.coroutine
    def handle_get_root(self, request):
        return self.make_response(request, data={
            'version': _version,
            'endpoints': {
                'players': {
                    'method': 'GET',
                    'href': '/players',
                },
                'world': {
                    'method': 'GET',
                    'href': '/world',
                },
                'server': {
                    'method': 'GET',
                    'href': '/server',
                },
            }
        })

    @route_info.handle_get('/server')
    @asyncio.coroutine
    def handle_get_server(self, request):
        actions = {}
        if self._mc_server.can_start:
            actions['start_server'] = {
                'method': 'POST',
                'href': '/server/start',
            }
        if self._mc_server.can_stop:
            actions['stop_server'] = {
                'method': 'POST',
                'href': '/server/stop',
            }
        return self.make_response(request, data={
            'stats': {
                'status_changed_at':
                    self._mc_server.status_changed_at.isoformat(),
                'status': self._mc_server.status,
            },
            'endpoints': actions,
        })

    @route_info.handle_get('/world')
    @asyncio.coroutine
    def handle_get_world(self, request):
        endpoints = {}
        if self._mc_server.status == 'stopped':
            endpoints['download_world'] = {
                'method': 'GET',
                'href': '/world/archive',
                'params': {
                    'format': {
                        'type': 'options',
                        'range': ['tar', 'zip']
                    }
                }
            }
            endpoints['upload_world'] = {
                'method': 'POST',
                'href': '/world/archive',
                'params': {
                    'archive': {'type': 'file'}
                }
            }
        return self.make_response(request, data={'endpoints': endpoints})

    @route_info.handle_get('/players')
    @asyncio.coroutine
    def handle_get_players(self, request):
        player_info = dict()
        for player in self._mc_server.players:
            player_info[player] = {
                'joined_at': self._mc_server.joined_at(player).isoformat()
            }
        last_part = self._mc_server.last_part_at
        return self.make_response(request, data={
            'last_part_at': last_part and last_part.isoformat(),
            'players': player_info,
        })

    @route_info.handle_post('/server/start')
    @asyncio.coroutine
    def handle_post_server_start(self, request):
        auth_request = yield from self.require_authentication(request)
        if auth_request:
            return auth_request
        if not self._mc_server.can_start:
            return (
                yield from self.method_not_allowed(
                    request,
                    allowed=[],
                    data={'server_status': self._mc_server.status},
                )
            )
        yield from self._mc_server.start(self._loop)
        return self.make_response(request)

    @route_info.handle_post('/server/stop')
    @asyncio.coroutine
    def handle_post_server_stop(self, request):
        auth_request = yield from self.require_authentication(request)
        if auth_request:
            return auth_request
        if not self._mc_server.can_stop:
            return (
                yield from self.method_not_allowed(
                    request,
                    allowed=[],
                    data={'server_status': self._mc_server.status}
                )
            )
        yield from self._mc_server.stop()
        return self.make_response(request)

    @route_info.handle_get('/world/archive')
    @asyncio.coroutine
    def handle_get_world_archive(self, request):
        if self._mc_server.status != 'stopped':
            return (
                yield from self.method_not_allowed(
                    request,
                    allowed=[],
                    data={'server_status': self._mc_server.status}
                )
            )
        try:
            yield from self._mc_server.acquire_read()
            if 'format' not in request.GET:
                return self.make_response(
                    request,
                    status=403,
                    data={
                        'reason': "missing parameter",
                        'detail': 'format',
                    }
                )
            response = ArchiveResponse.new(request.GET['format'])
            response.basename = 'minecraft_world'
            response.start(request)
            for filename, arcname in self._mc_server.world_files():
                yield from response.add(filename, arcname)
            yield from response.write_eof()
            return response
        finally:
            yield from self._mc_server.release_read()

    @route_info.handle_post('/world/archive')
    @asyncio.coroutine
    def handle_post_world_archive(self, request):
        auth_request = yield from self.require_authentication(request)
        if auth_request:
            return auth_request
        if self._mc_server.status != 'stopped':
            return (
                yield from self.method_not_allowed(
                    request,
                    allowed=[],
                    data={'server_status': self._mc_server.status}
                )
            )
        try:
            yield from self._mc_server.acquire_write()
            post_data = yield from request.post()
            if 'archive' not in post_data:
                return self.make_response(
                    request,
                    status=403,
                    data={
                        'reason': "missing parameter",
                        'detail': 'archive',
                    }
                )
            reader = archive.ArchiveReader.new(post_data['archive'].file)
            dirname = reader.find('level.dat')
            _logger.info("found level.dat in '%s'", dirname)
            yield from self._mc_server.world_extract(reader, dirname)
            return self.make_response(request)
        finally:
            yield from self._mc_server.release_write()

    @asyncio.coroutine
    def start(self, loop):
        app = web.Application(loop=loop)
        self.route_info.register_all(self, app.router)
        self._http_server = yield from loop.create_server(
            app.make_handler(),
            self._host, self._port)
        self._loop = loop

    @asyncio.coroutine
    def stop(self):
        self._http_server.close()
        yield from self._http_server.wait_closed()


class ArchiveResponse(web.StreamResponse):
    def __init__(self, make_archive_writer, status=200, headers=None):
        super().__init__(status=status)
        if headers:
            self.headers.extend(headers)
        self.__archive_writer = make_archive_writer(self)
        self.content_type = self.__archive_writer.mime_type

    @classmethod
    def new(cls, archive_format, status=200, headers=None):
        make_writer = None
        if archive_format == 'tar':
            make_writer = lambda fd: archive.TarWriter(fd, compression='gz')
        elif archive_format == 'zip':
            make_writer = lambda fd: archive.ZipWriter(fd)
        return cls(make_writer, status=status, headers=headers)

    @property
    def basename(self):
        return self.__archive_writer.basename

    @basename.setter
    def basename(self, basename):
        self.__archive_writer.basename = basename
        self.headers['Content-Disposition'] = \
            'attachment; filename={0}.{1}'.format(
                basename, self.__archive_writer.file_extension)

    @asyncio.coroutine
    def add(self, filename, arcname=None):
        yield from self.__archive_writer.add(filename, arcname)

    @asyncio.coroutine
    def write_eof(self):
        yield from self.__archive_writer.close()
        yield from super().write_eof()
