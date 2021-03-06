#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Contains the base objects for use when creating a sanitizer using
PyCIRCLean. Subclass or import from FileBase/KittenGroomerBase and implement
your desired behavior.
"""


import os
import hashlib
import shutil
import argparse

import magic


class KittenGroomerError(Exception):
    """Base KittenGroomer exception handler."""

    def __init__(self, message):
        super(KittenGroomerError, self).__init__(message)
        self.message = message


class ImplementationRequired(KittenGroomerError):
    """Implementation required error."""
    pass


class FileBase(object):
    """
    Base object for individual files in the source directory.

    Contains file attributes and various helper methods.
    """

    def __init__(self, src_path, dst_path):
        """
        Initialized with the source path and expected destination path.

        Create various properties and determine the file's mimetype.
        """
        self.src_path = src_path
        self.dst_path = dst_path
        self.filename = os.path.basename(self.src_path)
        self._file_props = {
            'filepath': self.src_path,
            'filename': self.filename,
            'file_size': self.size,
            'maintype': None,
            'subtype': None,
            'extension': None,
            'safety_category': None,
            'symlink': False,
            'copied': False,
            'description_string': [],  # array of descriptions to be joined
            'errors': {},
            'user_defined': {}
        }
        self.extension = self._determine_extension()
        self.set_property('extension', self.extension)
        self.mimetype = self._determine_mimetype()
        self.should_copy = True
        self.main_type = None
        self.sub_type = None
        if self.mimetype:
            self.main_type, self.sub_type = self._split_subtypes(self.mimetype)
            if self.main_type:
                self.set_property('maintype', self.main_type)
            if self.sub_type:
                self.set_property('subtype', self.sub_type)

    def _determine_extension(self):
        _, ext = os.path.splitext(self.src_path)
        ext = ext.lower()
        if ext == '':
            ext = None
        return ext

    def _determine_mimetype(self):
        if os.path.islink(self.src_path):
            # magic will throw an IOError on a broken symlink
            mimetype = 'inode/symlink'
            self.set_property('symlink', os.readlink(self.src_path))
        else:
            try:
                mt = magic.from_file(self.src_path, mime=True)
                # Note: libmagic will always return something, even if it's just 'data'
            except UnicodeEncodeError as e:
                # FIXME: The encoding of the file that triggers this is broken (possibly it's UTF-16 and Python expects utf8)
                # Note: one of the Travis files will trigger this exception
                self.add_error(e, '')
                mt = None
            try:
                mimetype = mt.decode("utf-8")
            except:
                mimetype = mt
        return mimetype

    def _split_subtypes(self, mimetype):
        if '/' in mimetype:
            main_type, sub_type = mimetype.split('/')
        else:
            main_type, sub_type = None, None
        return main_type, sub_type

    @property
    def size(self):
        """Filesize in bytes as an int, 0 if file does not exist."""
        try:
            size = os.path.getsize(self.src_path)
        except FileNotFoundError:
            size = 0
        return size

    @property
    def has_mimetype(self):
        """True if file has a main and sub mimetype, else False."""
        if not self.main_type or not self.sub_type:
            return False
        else:
            return True

    @property
    def has_extension(self):
        """True if self.extension is set, else False."""
        if self.extension is None:
            return False
        else:
            return True

    @property
    def is_dangerous(self):
        """True if file has been marked 'dangerous', else False."""
        return self._file_props['safety_category'] is 'dangerous'

    @property
    def is_unknown(self):
        """True if file has been marked 'unknown', else False."""
        return self._file_props['safety_category'] is 'unknown'

    @property
    def is_binary(self):
        """True if file has been marked 'binary', else False."""
        return self._file_props['safety_category'] is 'binary'

    @property
    def is_symlink(self):
        """True  if file is a symlink, else False."""
        if self._file_props['symlink'] is False:
            return False
        else:
            return True

    def set_property(self, prop_string, value):
        """
        Take a property and a value and add them to the file's property dict.

        If `prop_string` is part of the file property API, set it to `value`.
        Otherwise, add `prop_string`: `value` to `user_defined` properties.
        """
        if prop_string is 'description_string':
            if value not in self._file_props['description_string']:
                self._file_props['description_string'].append(value)
        elif prop_string in self._file_props.keys():
            self._file_props[prop_string] = value
        else:
            self._file_props['user_defined'][prop_string] = value

    def get_property(self, prop_string):
        """
        Get the value for a property stored on the file.

        Returns `None` if `prop_string` cannot be found on the file.
        """
        if prop_string in self._file_props:
            return self._file_props[prop_string]
        elif prop_string in self._file_props['user_defined']:
            return self._file_props['user_defined'][prop_string]
        else:
            return None

    def get_all_props(self):
        """Return a dict containing all stored properties of this file."""
        return self._file_props

    def add_error(self, error, info_string):
        """Add an `error`: `info_string` pair to the file."""
        self._file_props['errors'].update({error: info_string})

    def add_description(self, description_string):
        """
        Add a description string to the file.

        If `description_string` is already present, will prevent duplicates.
        """
        self.set_property('description_string', description_string)

    def make_dangerous(self, reason_string=None):
        """
        Mark file as dangerous.

        Prepend and append DANGEROUS to the destination file name
        to help prevent double-click of death.
        """
        if self.is_dangerous:
            self.set_property('description_string', reason_string)
            return
        self.set_property('safety_category', 'dangerous')
        self.set_property('description_string', reason_string)
        path, filename = os.path.split(self.dst_path)
        self.dst_path = os.path.join(path, 'DANGEROUS_{}_DANGEROUS'.format(filename))

    def make_unknown(self):
        """Mark file as an unknown type and prepend UNKNOWN to filename."""
        if self.is_dangerous or self.is_binary:
            return
        self.set_property('safety_category', 'unknown')
        path, filename = os.path.split(self.dst_path)
        self.dst_path = os.path.join(path, 'UNKNOWN_{}'.format(filename))

    def make_binary(self):
        """Mark file as a binary and append .bin to filename."""
        if self.is_dangerous:
            return
        self.set_property('safety_category', 'binary')
        path, filename = os.path.split(self.dst_path)
        self.dst_path = os.path.join(path, '{}.bin'.format(filename))

    def safe_copy(self, src=None, dst=None):
        """Copy file and create destination directories if needed."""
        if src is None:
            src = self.src_path
        if dst is None:
            dst = self.dst_path
        try:
            dst_path, filename = os.path.split(dst)
            if not os.path.exists(dst_path):
                os.makedirs(dst_path)
            shutil.copy(src, dst)
        except Exception as e:
            self.add_error(e, '')

    def force_ext(self, ext):
        """If dst_path does not end in ext, append .ext to it."""
        ext = self._check_leading_dot(ext)
        if not self.dst_path.endswith(ext):
            # LOG: do we want to log that the extension was changed as below?
            # self.set_property('force_ext', True)
            self.dst_path += ext
        if not self._file_props['extension'] == ext:
            self.set_property('extension', ext)

    def create_metadata_file(self, ext):
        """
        Create a separate file to hold extracted metadata.

        The string `ext` will be used as the extension for the metadata file.
        """
        ext = self._check_leading_dot(ext)
        try:
            if os.path.exists(self.src_path + ext):
                err_str = ("Could not create metadata file for \"" +
                           self.filename +
                           "\": a file with that path already exists.")
                raise KittenGroomerError(err_str)
            else:
                dst_dir_path, filename = os.path.split(self.dst_path)
                if not os.path.exists(dst_dir_path):
                    os.makedirs(dst_dir_path)
                self.metadata_file_path = self.dst_path + ext
                return self.metadata_file_path
        except KittenGroomerError as e:
            self.add_error(e, '')
            return False

    def _check_leading_dot(self, ext):
        if len(ext) > 0:
            if not ext.startswith('.'):
                return '.' + ext
        return ext


class Logging(object):

    @staticmethod
    def computehash(path):
        """Return the sha256 hash of a file at a given path."""
        s = hashlib.sha256()
        with open(path, 'rb') as f:
            while True:
                buf = f.read(0x100000)
                if not buf:
                    break
                s.update(buf)
        return s.hexdigest()


class KittenGroomerBase(object):
    """Base object responsible for copy/sanitization process."""

    def __init__(self, src_root_path, dst_root_path):
        """Initialized with path to source and dest directories."""
        self.src_root_path = os.path.abspath(src_root_path)
        self.dst_root_path = os.path.abspath(dst_root_path)

    def safe_rmtree(self, directory_path):
        """Remove a directory tree if it exists."""
        if os.path.exists(directory_path):
            shutil.rmtree(directory_path)

    def safe_remove(self, file_path):
        """Remove file at file_path if it exists."""
        if os.path.exists(file_path):
            os.remove(file_path)

    def safe_mkdir(self, directory_path):
        """Make a directory if it does not exist."""
        if not os.path.exists(directory_path):
            os.makedirs(directory_path)

    def list_all_files(self, directory_path):
        """Generator yielding path to all of the files in a directory tree."""
        for root, dirs, files in os.walk(directory_path):
            # files is a list anyway so we don't get much from using a generator here
            for filename in files:
                filepath = os.path.join(root, filename)
                yield filepath

    #######################

    # TODO: if we move main() we can get rid of this as well
    def processdir(self, src_dir, dst_dir):
        """Implement this function to define file processing behavior."""
        raise ImplementationRequired('Please implement processdir.')


# TODO: Should this get moved to filecheck? It isn't really API code and somebody can implement it themselves
def main(kg_implementation, description='Call a KittenGroomer implementation to process files present in the source directory and copy them to the destination directory.'):
    parser = argparse.ArgumentParser(prog='KittenGroomer', description=description)
    parser.add_argument('-s', '--source', type=str, help='Source directory')
    parser.add_argument('-d', '--destination', type=str, help='Destination directory')
    args = parser.parse_args()
    kg = kg_implementation(args.source, args.destination)
    kg.processdir()
