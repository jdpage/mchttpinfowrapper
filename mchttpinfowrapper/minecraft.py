"""Classes for Minecraft process management."""

# Copyright (C) 2015  Jonathan David Page
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program. If not, see <http://www.gnu.org/licenses/>.

import asyncio
import asyncio.subprocess
import logging
import re
import os
import os.path
import fcntl
import sys
from datetime import datetime

_logger = logging.getLogger(__name__)

_log_line_re = re.compile(
    r'''^''' +
    r'''\[(?P<hh>\d+):(?P<mm>\d+):(?P<ss>\d+)\] ''' +
    r'''\[(?P<thread>.*)/(?P<level>.*)\]''' +
    r''': ?(?P<msg>.*)$''')

_player_joined_re = re.compile(r'''^(?P<name>\w*) joined the game$''')
_player_left_re = re.compile(r'''^(?P<name>\w*) left the game$''')

# TODO: rewrite this as a subprocess protocol

class ServerWrapper:
    def __init__(self, mc_config):
        self._server_jar = os.path.abspath(mc_config.get('ServerJar'))
        self._java_flags = mc_config.get('JavaFlags', "").split()
        self._server_flags = mc_config.get('ServerFlags', "").split()
        self._working_dir = mc_config.get('WorkingDirectory', ".")

        self.process = None
        self._mc_logger = logging.getLogger(__name__ + '.process')
        self._input_stream = None
        self._input_task = None
        self._output_task = None

        self._start_time = datetime.now()
        self._last_part = None
        self._players = dict()
        self._log_events = []
        self.add_log_event(_player_joined_re, self._player_joined_callback)
        self.add_log_event(_player_left_re, self._player_left_callback)

    def get_server_cmd_line(self):
        line = ["java"]
        line.extend(self._java_flags)
        line.append("-jar")
        line.append(self._server_jar)
        line.extend(self._server_flags)
        return line

    @staticmethod
    def parse_log_level(level):
        if level == 'ERROR':
            return 40
        elif level == 'WARNING':
            return 30
        elif level == 'INFO':
            return 20
        _logger.warn("Unknown log level '%s'", level)
        return 20

    def add_log_event(self, pattern, callback):
        e = (pattern, callback)
        self._log_events.append(e)
        return e

    def remove_log_event(self, e):
        self._log_events.remove(e)

    @asyncio.coroutine
    def trigger_log_events(self, msg):
        suppress = False
        for pattern, callback in self._log_events:
            m = pattern.match(msg)
            if m:
                result = callback(m)
                if asyncio.iscoroutine(result):
                    result = yield from result
                suppress = suppress or result
        return suppress

    @asyncio.coroutine
    def handle_log_line(self, line):
        if line.strip() == '':
            return
        m = _log_line_re.match(line)
        if m:
            level = self.parse_log_level(m.group('level'))
            msg = m.group('msg')
            if not (yield from self.trigger_log_events(msg)):
                self._mc_logger.log(level, "(%s) %s", m.group('thread'), msg)
        else:
            self._mc_logger.warn(line)

    @asyncio.coroutine
    def start(self):
        _logger.info("Preparing to start Minecraft server process")
        if not os.path.isdir(self._working_dir):
            _logger.info("working directory does not exist")
            os.mkdir(self._working_dir)
            _logger.info("created working directory '%s'", self._working_dir)
        eula = os.path.join(self._working_dir, 'eula.txt')
        _logger.info("Agreeing to EULA")
        with open(eula, 'w') as f:
            f.write("eula=true")
        old_wd = os.getcwd()
        os.chdir(self._working_dir)
        _logger.info("Starting Minecraft server process")
        self.process = yield from asyncio.create_subprocess_exec(
            *self.get_server_cmd_line(),
            stdout=asyncio.subprocess.PIPE,
            stdin=asyncio.subprocess.PIPE)
        os.chdir(old_wd)

    @asyncio.coroutine
    def wait(self):
        yield from self.process.wait()
        _logger.info("Minecraft server stopped")
        self._input_task.cancel()
        self._output_task.cancel()

    def handle_io(self, loop=None):
        if not loop:
            loop = asyncio.get_event_loop()

        self._input_stream = asyncio.StreamReader(loop=loop)

        # make sys.stdin non-blocking
        flags = fcntl.fcntl(sys.stdin.fileno(), fcntl.F_GETFL)
        fcntl.fcntl(sys.stdin.fileno(), fcntl.F_SETFL, flags | os.O_NONBLOCK)

        loop.add_reader(sys.stdin.fileno(), self.relay_input, sys.stdin)
        self._input_task = loop.create_task(self.handle_input())
        self._output_task = loop.create_task(self.handle_output())

    def relay_input(self, stream):
        while stream.readable():
            data = stream.read(1024)
            if data and len(data) > 0:
                data = data.encode()
                self._input_stream.feed_data(data)
            else:
                break

    @asyncio.coroutine
    def handle_output(self):
        data = True
        while data:
            data = yield from self.process.stdout.readline()
            line = data.decode('utf-8').rstrip()
            yield from self.handle_log_line(line)

    @asyncio.coroutine
    def handle_input(self):
        data = True
        while data:
            data = yield from self._input_stream.readline()
            if data == b'll\n':
                _logger.info(str(self.players()))
            else:
                self.process.stdin.write(data)
                yield from self.process.stdin.drain()

    @asyncio.coroutine
    def send_command(self, line):
        """Sends a line to the server process."""
        # because handle_input only sends input line-by-line, we can safely
        # send any lines we like without worrying about corrupting the stream
        self.process.stdin.write("{0}\n".format(line).encode())
        yield from self.process.stdin.drain()

    @asyncio.coroutine
    def send_command_and_wait(self, line, pattern, suppress=True):
        """Sends a line to the server, then waits for a response."""
        sem = asyncio.Semaphore(value=0)
        mm = None
        e = None

        @asyncio.coroutine
        def callback(m):
            nonlocal mm
            self.remove_log_event(e)
            mm = m
            yield from sem.release()
            return suppress

        e = self.add_log_event(pattern, callback)

        # now that we're prepared for the response, we can send the command and
        # wait for the response without worrying about missing it
        yield from self.send_command(line)
        yield from sem.acquire()
        return mm

    @asyncio.coroutine
    def stop(self):
        """Stops the server.

        Functions by sending the string 'stop' to the server via stdin."""

        yield from self.send_command('stop')

    def uptime(self):
        return datetime.now() - self._start_time

    def _player_joined_callback(self, m):
        self._players[m.group('name')] = datetime.now()

    def _player_left_callback(self, m):
        del self._players[m.group('name')]
        self._last_part = datetime.now()

    def players(self):
        return list(self._players.keys())

    def time_since_joined(self, player):
        return datetime.now() - self._players[player]

    def time_since_last_part(self):
        if self._last_part:
            return datetime.now() - self._last_part
        return None
