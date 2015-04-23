"""Classes for interacting with Mojang account."""

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
import aiohttp
import simplejson as json
import os.path
import uuid


_authenticate_url = "https://authserver.mojang.com/authenticate"
_refresh_url = "https://authserver.mojang.com/refresh"
_invalidate_url = "https://authserver.mojang.com/invalidate"


class AuthenticationException(Exception):
    def __init__(self, error: str, message: str) -> None:
        super().__init__(message)
        self.error = error


class MojangClient:
    @classmethod
    @asyncio.coroutine
    def request(cls, method, url, data):
        r = yield from aiohttp.request(method, url,
                                       headers={'Content-type':
                                                'application/json'},
                                       data=json.dumps(data))
        response = yield from r.text()
        if response and response != '':
            return cls.handle_errors(json.loads(response))
        return None

    @staticmethod
    def handle_errors(response):
        if response and 'error' in response and response['error'] != '':
                raise AuthenticationException(response['error'],
                                              response['errorMessage'])
        return response


class AuthenticationClient(MojangClient):
    def __init__(self, state_file):
        self._state_file = state_file
        self.client_token = None
        if os.path.isfile(state_file):
            with open(state_file) as f:
                state = json.load(f)
                if 'mojang' in state and 'client_token' in state['mojang']:
                    self.client_token = state['mojang']['client_token']
        if self.client_token is None:
            self.client_token = uuid.uuid4().hex

    def save(self):
        state = {}
        if os.path.isfile(self._state_file):
            with open(self._state_file) as f:
                state = json.load(f)
        if 'mojang' not in state:
            state['mojang'] = {}
        state['mojang']['client_token'] = self.client_token
        with open(self._state_file, 'w') as f:
            json.dump(state, f)

    @asyncio.coroutine
    def authenticate(self, username, password):
        response = yield from self.request('post', _authenticate_url, {
            'agent': {
                'name': "Minecraft",
                'version': "1",
            },
            'username': username,
            'password': password,
            'clientToken': self.client_token,
        })
        return AccessToken(self, response['accessToken'])

    def __repr__(self):
        return "{0}({1})".format(type(self).__name__, repr(self._state_file))


class AccessToken(MojangClient):
    def __init__(self, client, token_str):
        self.client = client
        self.token_str = token_str

    @asyncio.coroutine
    def refresh(self):
        response = yield from self.request('post', _refresh_url, {
            'clientToken': self.client.client_token,
            'accessToken': self.token_str,
            'selectedProfile': None,
        })
        self.token_str = response['accessToken']

    @asyncio.coroutine
    def invalidate(self):
        yield from self.request('post', _invalidate_url, {
            'accessToken': self.token_str,
            'clientToken': self.client.client_token,
        })

    def __repr__(self):
        return "{0}({1}, {2})".format(type(self).__name__,
                                      repr(self.client),
                                      repr(self.token_str))
