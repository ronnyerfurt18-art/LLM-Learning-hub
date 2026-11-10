"""Extension boundary for future LOCAL providers. Disabled; no hidden connections."""
from typing import Protocol


class LocalLearningProvider(Protocol):
    def generate_questions(self, source_text: str) -> list[dict]: ...
    def assess_answer(self, question: dict, answer: str) -> dict: ...


class DisabledProvider:
    enabled = False
    name = 'none'

    def generate_questions(self, source_text):
        raise RuntimeError('Lokale KI ist nicht konfiguriert. Bitte JSON-Import verwenden.')

    def assess_answer(self, question, answer):
        raise RuntimeError('Lokale KI ist nicht konfiguriert. Schlagworthinweise und Selbstbewertung sind verfügbar.')
