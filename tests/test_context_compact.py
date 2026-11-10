"""Compact context for local models: budget setting and focused PDF passages."""
import unittest

from backend.tutor_context import (DEFAULT_LOCAL_CONTEXT_CHARS, MAX_CONTEXT_CHARS, MIN_LOCAL_CONTEXT_CHARS,
                                   _term_weights, _terms, focused_text, local_context_chars)


class LocalBudgetTests(unittest.TestCase):
    def test_default_override_and_full_context(self):
        self.assertEqual(local_context_chars({}), DEFAULT_LOCAL_CONTEXT_CHARS)
        self.assertEqual(local_context_chars({'MLH_LOCAL_CONTEXT_CHARS': '12000'}), 12000)
        self.assertEqual(local_context_chars({'MLH_LOCAL_CONTEXT_CHARS': '0'}), MAX_CONTEXT_CHARS)
        self.assertEqual(local_context_chars({'MLH_LOCAL_CONTEXT_CHARS': '99999'}), MAX_CONTEXT_CHARS)
        self.assertEqual(local_context_chars({'MLH_LOCAL_CONTEXT_CHARS': '500'}), MIN_LOCAL_CONTEXT_CHARS)
        self.assertEqual(local_context_chars({'MLH_LOCAL_CONTEXT_CHARS': 'viel'}), DEFAULT_LOCAL_CONTEXT_CHARS)


class FocusedTextTests(unittest.TestCase):
    page = ('Kapitel 3 Informatik-Strategie\n\n'
            + 'Die Kantine bietet montags Suppe an und schließt um vierzehn Uhr. ' * 12 + '\n\n'
            + 'Die Situationsanalyse bestimmt die strategische Rolle der IT mit dem Informationsintensitätenportfolio.\n\n'
            + 'Parkplätze stehen hinter dem Gebäude zur Verfügung, solange der Vorrat reicht. ' * 12 + '\n\n'
            + 'In der Umfeldanalyse folgen Wettbewerbsanalyse und Informationsarchitekturanalyse.')

    def test_matching_passages_kept_in_order_and_unrelated_dropped(self):
        terms = _term_weights('Strategieprozess: Situationsanalysen und Umfeldanalyse, Informationsarchitektur')
        result = focused_text(self.page, terms, 600)
        self.assertIsNotNone(result)
        self.assertLessEqual(len(result), 600)
        self.assertIn('Situationsanalyse bestimmt', result)
        self.assertIn('Umfeldanalyse folgen', result)
        self.assertLess(result.index('Situationsanalyse'), result.index('Umfeldanalyse'))
        self.assertNotIn('Kantine', result)
        self.assertNotIn('Parkplätze', result)
        self.assertIn('[…]', result)
        self.assertIn('passenden Stellen', result)

    def test_falls_back_when_page_is_short_or_nothing_matches(self):
        self.assertIsNone(focused_text('Kurzer Text.', _terms('Situationsanalyse'), 600))
        self.assertIsNone(focused_text(self.page, set(), 600))
        self.assertIsNone(focused_text(self.page, _term_weights('Quantenchromodynamik Gluonen'), 600))

    def test_long_single_line_is_split_at_sentences(self):
        line = 'Füllsatz über das Wetter am Morgen. ' * 60 + 'Die Lernnotiz zur Wochenplanung steht hier. ' + 'Noch ein Wettersatz. ' * 60
        result = focused_text(line, _term_weights('Lernnotiz und Wochenplanung'), 400)
        self.assertIsNotNone(result)
        self.assertIn('Lernnotiz zur Wochenplanung', result)
        self.assertLessEqual(len(result), 400)

    def test_weak_generic_matches_are_not_sent(self):
        noise = ('Die Studie untersucht und unterscheidet verwendete Ergebnisse sehr genau. ' * 30 + '\n\n'
                 + 'Wetter und Kantine bestimmen den Tag. ' * 30)
        self.assertIsNone(focused_text(noise, _term_weights('Unterschiede untersuchen, Ergebnisse verwenden, Situationsanalyse'), 500))

    def test_compound_terms_weigh_double(self):
        weights = _term_weights('Situationsanalyse Rolle')
        self.assertEqual(weights['situati'], 2)
        self.assertEqual(weights['rolle'], 1)

    def test_stopwords_and_short_words_do_not_count(self):
        self.assertFalse(_terms('und oder aber nicht eine der die das'))
        self.assertIn(_terms('Situationsanalysen').pop(), _terms('Situationsanalyse'))


if __name__ == '__main__':
    unittest.main()
