"""Small, expiring cache of extracted pages; never retain readers or file handles.

Callers must resolve/authorize the source before every lookup. File identity and
metadata invalidate entries on edits/replacements. MLH_PDF_TEXT_CACHE=0 bypasses
the cache for comparison or rollback without changing retrieval.
"""
from collections import OrderedDict
import os
import threading
import time


class PageTextCache:
    def __init__(self, max_bytes=4 * 1024 * 1024, max_pages=256, ttl=120, clock=time.monotonic):
        self.max_bytes, self.max_pages, self.ttl = max_bytes, max_pages, ttl
        self.clock = clock
        self._entries = OrderedDict()
        self._bytes = 0
        self._lock = threading.Lock()

    @staticmethod
    def _version(path):
        stat = path.stat()
        return stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns

    def _drop(self, key):
        self._bytes -= self._entries.pop(key)[3]

    def get(self, path, page, loader):
        if os.environ.get('MLH_PDF_TEXT_CACHE', '1') == '0':
            return loader()
        key = (str(path), page)
        version, now = self._version(path), self.clock()
        with self._lock:
            for old_key, entry in list(self._entries.items()):
                if now - entry[0] >= self.ttl:
                    self._drop(old_key)
            entry = self._entries.get(key)
            if entry and entry[1] == version:
                self._entries.move_to_end(key)
                return entry[2]
            if entry:
                self._drop(key)
        text = loader()  # exceptions are not cached; extraction does not hold the lock
        size = len(text.encode('utf-8'))
        if self._version(path) != version:
            raise ValueError('Quelldatei hat sich während des Lesens geändert.')
        if size > self.max_bytes or self.max_pages < 1:
            return text
        with self._lock:
            if key in self._entries:
                self._drop(key)
            while self._entries and (self._bytes + size > self.max_bytes or len(self._entries) >= self.max_pages):
                self._drop(next(iter(self._entries)))
            self._entries[key] = (self.clock(), version, text, size)
            self._bytes += size
        return text


PAGE_TEXT_CACHE = PageTextCache()
