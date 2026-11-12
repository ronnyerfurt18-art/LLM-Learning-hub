"""Cached extraction must preserve retrieval and react to file changes."""
import os
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from backend.pdf_text_cache import PageTextCache
from backend.tutor_context import build_tutor_context
from tests import test_tutor_context as base

text_pdf = base.text_pdf


def test_cache_reuses_text_and_invalidates_replaced_file(tmp_path):
    path = tmp_path / 'source.pdf'
    path.write_text('old')
    cache = PageTextCache()
    load = Mock(side_effect=['old', 'new'])
    assert cache.get(path, 1, load) == cache.get(path, 1, load) == 'old'
    replacement = tmp_path / 'replacement'
    replacement.write_text('new')
    replacement.replace(path)
    assert cache.get(path, 1, load) == 'new'
    assert load.call_count == 2
    path.unlink()
    with pytest.raises(FileNotFoundError):
        cache.get(path, 1, load)


def test_budget_expiry_bypass_and_failures(tmp_path):
    path = tmp_path / 'source.pdf'
    path.touch()
    clock = Mock(return_value=0)
    cache = PageTextCache(max_bytes=8, max_pages=2, ttl=10, clock=clock)
    load = Mock(return_value='abcd')
    for page in (1, 2, 1, 3, 2):
        cache.get(path, page, load)
    assert load.call_count == 4  # page 2 was least recently used
    clock.return_value = 11
    cache.get(path, 2, load)
    assert load.call_count == 5
    with patch.dict(os.environ, {'MLH_PDF_TEXT_CACHE': '0'}):
        cache.get(path, 2, load)
    assert load.call_count == 6
    big = Mock(return_value='x' * 9)
    cache.get(path, 4, big)
    cache.get(path, 4, big)
    assert big.call_count == 2
    fail = Mock(side_effect=ValueError('unreadable'))
    for _ in range(2):
        with pytest.raises(ValueError):
            cache.get(path, 5, fail)
    assert fail.call_count == 2


def test_change_during_extraction_is_not_returned(tmp_path):
    path = tmp_path / 'source.pdf'
    path.write_text('old')
    def changed():
        path.write_text('changed')
        return 'old'
    with pytest.raises(ValueError, match='geändert'):
        PageTextCache().get(path, 1, changed)


class ContextCacheTests(unittest.TestCase):
    setUp = base.TutorContextTests.setUp
    write_content = base.TutorContextTests.write_content
    context = base.TutorContextTests.context
    def test_cached_context_is_identical_and_keeps_citations(self):
        with patch.dict(os.environ, {'MLH_PDF_TEXT_CACHE': '0'}):
            baseline = self.context(lesson_id='lektion-a', max_chars=9000, message='Erkläre A.')
        first = self.context(lesson_id='lektion-a', max_chars=9000, message='Erkläre A.')
        with patch('backend.tutor_context.PdfReader', side_effect=AssertionError('page should be cached')):
            warm = self.context(lesson_id='lektion-a', max_chars=9000, message='Erkläre A.')
        assert baseline == first == warm
        text_pdf(self.pdf, ['Neuer Text.' for _ in range(12)])
        changed = self.context(lesson_id='lektion-a', max_chars=9000)
        assert 'Neuer Text.' in changed['context_text']
        assert changed['sources'] == baseline['sources']
