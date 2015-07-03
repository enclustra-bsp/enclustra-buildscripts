import os
import tarfile
import zipfile


class ArchiveException(Exception):
    """Base exception class for all archive errors."""

class UnrecognizedArchiveFormat(ArchiveException):
    """Error raised when passed file is not a recognized archive format."""

class UnsafeArchive(ArchiveException):
    """Error raised when passed file contains absolute paths which could be
    extracted outside of the target directory."""


def extract(path, to_path='', safe=False, filename=None):
    """
    Unpack the tar or zip file at the specified path to the directory
    specified by to_path.
    """
    Archive(path, filename).extract(to_path, safe)


class Archive(object):
    """
    The external API class that encapsulates an archive implementation.
    """

    def __init__(self, file, filename=None):
        self._archive = self._archive_cls(file, filename)(file)

    @staticmethod
    def _archive_cls(file, filename=None):
        cls = None
        if not filename:
            if isinstance(file, basestring):
                filename = file
            else:
                try:
                    filename = file.name
                except AttributeError:
                    raise UnrecognizedArchiveFormat(
                        "File object not a recognized archive format.")
        base, tail_ext = os.path.splitext(filename.lower())
        cls = extension_map.get(tail_ext)
        if not cls:
            base, ext = os.path.splitext(base)
            cls = extension_map.get(ext)
        if not cls:
            raise UnrecognizedArchiveFormat(
                "Path not a recognized archive format: %s" % filename)
        return cls

    def extract(self, to_path='', safe=False):
        if safe:
            to_abspath = os.path.abspath(to_path)
            for name in self._archive.namelist():
                dest = os.path.join(to_path, name)
                if not os.path.abspath(dest).startswith(to_abspath):
                    raise UnsafeArchive("Unsafe destination path " \
                            "(outside of the target directory)")
        self._archive.extract(to_path)

    def namelist(self):
        return self._archive.namelist()

    def printdir(self):
        self._archive.printdir()


class BaseArchive(object):
    """
    Base Archive class.  Implementations should inherit this class.
    """

    def extract(self):
        raise NotImplementedError

    def namelist(self):
        raise NotImplementedError

    def printdir(self):
        raise NotImplementedError


class TarArchive(BaseArchive):

    def __init__(self, file):
        self._archive = tarfile.open(file) if isinstance(file, basestring) \
                else tarfile.open(fileobj=file)

    def printdir(self, *args, **kwargs):
        self._archive.list(*args, **kwargs)

    def namelist(self, *args, **kwargs):
        return self._archive.getnames(*args, **kwargs)

    def extract(self, to_path=''):
        self._archive.extractall(to_path)


class ZipArchive(BaseArchive):

    def __init__(self, file):
        self._archive = zipfile.ZipFile(file)

    def printdir(self, *args, **kwargs):
        self._archive.printdir(*args, **kwargs)

    def namelist(self, *args, **kwargs):
        return self._archive.namelist(*args, **kwargs)

    def extract(self, to_path='', safe=False):
        self._archive.extractall(to_path)


extension_map = {
    '.egg': ZipArchive,
    '.jar': ZipArchive,
    '.tar': TarArchive,
    '.tar.bz2': TarArchive,
    '.tar.gz': TarArchive,
    '.tgz': TarArchive,
    '.tz2': TarArchive,
    '.zip': ZipArchive,
}
