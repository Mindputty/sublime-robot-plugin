import os
from copy import copy
from collections import deque
from time import time

import sublime

from robot.api import TestCaseFile, ResourceFile
from robot.errors import DataError

from scanner_cache import ScannerCache


scanner_cache = ScannerCache()

SCAN_TIMEOUT = 5 # seconds

class WrappedKeyword:
    def __init__(self, data_file, keyword, file_path):
        self.keyword = keyword
        self.name = data_file.name + '.' + keyword.name
        self.file_path = file_path
        self.description = []
        args = ', '.join(keyword.args.value)
        if args:
            self.description.append(args)
        if keyword.doc.value:
            self.description.append(keyword.doc.value)
        self.description.append(file_path)

    def show_definition(self, view, views_to_center):
        source_path = self.keyword.source
        new_view = view.window().open_file("%s:%d" % (source_path, self.keyword.linenumber), sublime.ENCODED_POSITION)
        new_view.show_at_center(new_view.text_point(self.keyword.linenumber, 0))
        if new_view.is_loading():
            views_to_center[new_view.id()] = self.keyword.linenumber

    def __eq__(self, other):
        return isinstance(other, WrappedKeyword) and self.file_path == other.file_path

    def allow_unprompted_go_to(self):
        return True


class Scanner(object):

    def __init__(self, view):
        self.view = view

    def scan_file(self, data_file):
        self.start_time = time()
        self.start_path = data_file.directory
        keywords = {}
        self.__scan_file(keywords, data_file, deque())
        return keywords

    def __scan_file(self, keywords, data_file, import_history):
        if time() - self.start_time > SCAN_TIMEOUT:
            sublime.set_timeout(lambda: self.view.set_status('scan_error', 'scanning timeout exceeded'), 0)
            sublime.set_timeout(lambda: self.view.erase_status('scan_error'), 5000)
            return
        if data_file.source in import_history:
            # prevent circular import loops
            return
        import_history = copy(import_history)
        import_history.append(data_file.source)

        for setting in data_file.imports:
            if hasattr(setting, 'type'):
                if setting.type == 'Resource':
                    resource_path = os.path.normpath(os.path.join(setting.directory, setting.name))
                    cached = scanner_cache.get_cached_data(resource_path)
                    if cached:
                        self.__scan_file(keywords, cached, import_history)
                    else:
                        try:
                            resource_data = ResourceFile(source=resource_path).populate()
                            scanner_cache.put_data(resource_path, resource_data)
                            self.__scan_file(keywords, resource_data, import_history)
                        except DataError as de:
                            print 'error reading resource:', resource_path

        for keyword in data_file.keyword_table:
            lower_name = keyword.name.lower()
            if not keywords.has_key(lower_name):
                keywords[lower_name] = []
            wrapped = WrappedKeyword(data_file, keyword, os.path.relpath(keyword.source, self.start_path))
            if wrapped in keywords[lower_name]:
                continue
            keywords[lower_name].append(wrapped)