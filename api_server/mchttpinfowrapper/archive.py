"""Classes for archive management."""

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
import os.path
import tarfile
import zipfile
import zipstream
import logging
import io
import shutil

_logger = logging.getLogger(__name__)


class ArchiveWriter(metaclass=ABCMeta):
    def __init__(self) -> None:
        self.basename = None

    @property
    @abstractmethod
    def mime_type(self) -> str:
        return None

    @property
    @abstractmethod
    def file_extension(self) -> str:
        return None

    @asyncio.coroutine
    @abstractmethod
    def add(self, filename: str, arcname=None):
        pass

    @asyncio.coroutine
    @abstractmethod
    def close(self):
        pass


class ZipWriter(ArchiveWriter):
    def __init__(self, fd):
        super().__init__()
        self.fd = fd
        self.zip_stream = zipstream.ZipFile(
            mode='w', compression=zipstream.ZIP_DEFLATED)

    @property
    def mime_type(self):
        return 'application/zip'

    @property
    def file_extension(self):
        return 'zip'

    @asyncio.coroutine
    def add(self, filename, arcname=None):
        self.zip_stream.write(filename, arcname=arcname)
        yield from self.fd.drain()

    @asyncio.coroutine
    def close(self):
        if self.zip_stream:
            for chunk in self.zip_stream:
                self.fd.write(chunk)
                yield from self.fd.drain()
            self.zip_stream.close()
            self.zip_stream = None


class TarWriter(ArchiveWriter):
    def __init__(self, fd, compression=None):
        super().__init__()
        self.fd = fd
        self.compression = compression
        self.tar_stream = tarfile.open(fileobj=fd,
                                       mode=self.compression_mode('w'))

    def compression_mode(self, base_mode):
        return ((self.compression
                 and base_mode + ':' + self.compression)
                or base_mode)

    @property
    def mime_type(self):
        if self.compression is None:
            return 'application/x-tar'
        elif self.compression == 'gz':
            return 'application/x-gzip'

    @property
    def file_extension(self):
        if self.compression is None:
            return 'tar'
        elif self.compression == 'gz':
            return 'tar.gz'

    @asyncio.coroutine
    def add(self, filename, arcname=None):
        if not arcname:
            filename = arcname
        if self.basename:
            arcname = os.path.join(self.basename, arcname)
        self.tar_stream.add(filename, arcname=arcname, recursive=False)
        yield from self.fd.drain()

    @asyncio.coroutine
    def close(self):
        self.tar_stream.close()
        yield from self.fd.drain()


class ArchiveReader(metaclass=ABCMeta):
    @abstractmethod
    def reset(self) -> None:
        pass

    @abstractmethod
    def current_file(self) -> io.BufferedReader:
        pass

    @abstractmethod
    def __next__(self) -> str:
        # it's imperative that this returns directories with the slash at the
        # end, otherwise everything breaks
        pass

    def __iter__(self):
        self.reset()
        return self

    def find(self, filename):
        for member in self:
            member = os.path.normcase(os.path.normpath(member))
            dirname, basename = os.path.split(member)
            if basename == filename:
                return dirname
        return None

    def extract_into(self, dst_file):
        with self.current_file() as src_file:
            shutil.copyfileobj(fsrc=src_file, fdst=dst_file)

    @staticmethod
    def new(file):
        sig = file.read(4)
        file.seek(0)
        # try to guess what kind of file it is
        if sig == bytes([0x50, 0x4b, 0x03, 0x04]):
            # is a ZIP file
            return ZipReader(file)
        elif sig[:3] == bytes([0x1f, 0x8b, 0x08]):
            # is a GZIP file
            return TarReader(file)
        return None


class TarReader(ArchiveReader):
    def __init__(self, file: io.BytesIO) -> None:
        self.archive = tarfile.open(fileobj=file)
        self.members = iter(self.archive.getmembers())
        self.current_info = None

    def reset(self) -> None:
        self.members = iter(self.archive.getmembers())

    def current_file(self) -> io.BufferedReader:
        return self.archive.extractfile(self.current_info)

    def __next__(self) -> str:
        while True:
            try:
                self.current_info = next(self.members)
            except StopIteration:
                self.current_info = None
                raise

            if self.current_info.isdir():
                name = self.current_info.name
                if not name.endswith('/'):
                    name += '/'
                return name
            elif self.current_info.isfile():
                return self.current_info.name


class ZipReader(ArchiveReader):
    def __init__(self, file: io.BytesIO):
        self.archive = zipfile.ZipFile(file)
        self.members = iter(self.archive.infolist())
        self.current_info = None

    def reset(self):
        self.members = iter(self.archive.infolist())

    def current_file(self):
        return self.archive.open(self.current_info)

    def __next__(self):
        while True:
            try:
                self.current_info = next(self.members)
            except StopIteration:
                self.current_info = None
                raise

            return self.current_info.filename
