"""Tutor context for one question of a prepared assignment (Einsendearbeit).

The free tutor chat only knows the selected learning page. When the learner asks
to prepare an assignment, the hub selects the question, adds its statements, the
derived classification with reasons and the cited course pages, and keeps track
of which questions were opened in the chat. The model itself stores nothing.
"""
import hashlib
import re
from datetime import date, datetime, timezone

from .assignments import assignments_for_module
from .quality import REPAIR_PREFIX
from .tutor_context import (MAX_CONTEXT_CHARS, MIN_LOCAL_CONTEXT_CHARS, _CuratedContext, _DATA_NOTICE, _END,
                            _pdf_excerpts, _position, _short, _term_weights, _utf16_index)

STATE_KEY = 'tutor:assignments'
_MENTION = re.compile(r'einsende\w*|\bea\s*\d', re.I)
_ASSIGNMENT_NUMBER = re.compile(r'(?:einsende\w*|\bea)\s*(?:nr\.?\s*)?(\d)\b', re.I)
_QUESTION_NUMBER = re.compile(r'(?:aufgabe|frage)\s*(?:nr\.?\s*|nummer\s*)?(\d{1,2})\b', re.I)
_NEXT = re.compile(r'n[aä]chste\w*\s+(?:aufgabe|frage)|(?:aufgabe|frage)\s+weiter|weiter\s+(?:mit|zur)\s+(?:der\s+)?n[aä]chsten', re.I)


def _last(pattern, texts):
    for text in texts:
        found = pattern.findall(text)
        if found:
            return int(found[-1])
    return None


def _fingerprint(text):
    return hashlib.sha256(text.encode('utf-8')).hexdigest()[:16]


def select_question(hub, module, project_root, source_root, message, history, now=None):
    """Assignment, question and stored progress for this turn, or None outside assignment work."""
    now = now or datetime.now(timezone.utc)
    turns = [message] + [turn['content'] for turn in reversed(history) if turn['role'] == 'user']
    saved = (hub.get_meta(STATE_KEY) or {}).get(module['id'], {})
    active = saved.get('active') or {}
    # The same conversation continues when its previous message is still in the history,
    # even after the first mention of the assignment has left the short history window.
    continued = bool(active.get('turn')) and any(_fingerprint(text) == active['turn'] for text in turns[1:])
    if not continued and not any(_MENTION.search(text) for text in turns):
        return None
    assignments = assignments_for_module(module, project_root, source_root)
    if not assignments:
        return None
    wanted = _last(_ASSIGNMENT_NUMBER, turns)
    assignment = (assignments[wanted - 1] if wanted and 1 <= wanted <= len(assignments) else
                  next((item for item in assignments if item['id'] == active.get('assignment')), None) or
                  next((item for item in assignments if date.fromisoformat(item['due_date']) >= now.date()), assignments[0]))
    total = len(assignment['questions'])
    current = active.get('question') if active.get('assignment') == assignment['id'] else None
    # A prepared correction quotes findings; numbers inside it do not switch the question.
    repair = message.startswith(REPAIR_PREFIX)
    number = None if repair else _last(_QUESTION_NUMBER, [message])
    if number is None and not repair and _NEXT.search(message) and current:
        number = current + 1
    if number is None:
        number = current or _last(_QUESTION_NUMBER, turns[1:]) or 1
    number = max(1, min(total, number))
    discussed = sorted(int(key) for key in saved.get('discussed', {}).get(assignment['id'], {}))
    # A question is opened anew when the chat moves to it or a new conversation resumes it.
    opened = not (continued and current == number)
    return {'assignment': assignment, 'question': assignment['questions'][number - 1], 'number': number,
            'opened': opened, 'discussed': [item for item in discussed if item != number]}


def remember_question(hub, module_id, selection, message='', now=None):
    """Record the opened question; this is the chat's only write and holds no assessment."""
    now = (now or datetime.now(timezone.utc)).isoformat()
    state = hub.get_meta(STATE_KEY) or {}
    saved = state.setdefault(module_id, {})
    assignment_id = selection['assignment']['id']
    saved['active'] = {'assignment': assignment_id, 'question': selection['number'], 'at': now, 'turn': _fingerprint(message)}
    saved.setdefault('discussed', {}).setdefault(assignment_id, {}).setdefault(str(selection['number']), now)
    hub.set_meta(STATE_KEY, state)


def build_assignment_context(selection, module_id, project_root, source_root, max_chars=None):
    """Same contract as build_tutor_context, filled with one assignment question."""
    assignment, question, number = selection['assignment'], selection['question'], selection['number']
    total = len(assignment['questions'])
    count = len(question['options'])
    letters = f"A bis {question['options'][-1]['id']}"
    title = f"{assignment['title']} · Frage {number} von {total}: {question['title']}"
    open_numbers = [item for item in range(1, total + 1) if item != number and item not in selection['discussed']]
    lead = (
        f"EINSENDEARBEIT-MODUS (Hinweis des Lernhubs, keine Lerndaten): Die lernende Person bereitet {assignment['title']} vor "
        f"(Abgabe {date.fromisoformat(assignment['due_date']).strftime('%d.%m.%Y')}). Aktuell: Frage {number} von {total}.\n"
        + ('Diese Frage wird jetzt neu geöffnet. Beginne deine Antwort mit der Überschrift der Frage und allen ' + f'{count} Aussagen {letters} '
           'im vollständigen Wortlaut als Liste, noch ohne Einordnung. Vermittle danach knapp den Stoff, den die Frage verlangt, '
           'anhand der beigefügten Belegstellen, und bitte dann um die Einschätzung der ersten beiden Aussagen.\n'
           if selection.get('opened', True) else
           'Die Frage ist bereits geöffnet; setze das Gespräch fort.\n')
        + 'Vorgehen: Gehe die Aussagen einzeln durch, höchstens zwei pro Antwort. Nenne jede Aussage im vollständigen Wortlaut, bevor du '
        'nach einer Einschätzung fragst oder sie auflöst; setze nie voraus, dass die Person den Wortlaut kennt. Lass sie erst selbst '
        'einschätzen, ob die Aussage wahr oder falsch ist und warum. Löse dann auf und erkläre bei falschen Aussagen genau, welcher Teil '
        'nicht stimmt und wie es laut Lehrbrief richtig heißt.\n'
        'Fragt die Person nach dem Wortlaut, den Aussagen, den Antworten oder der Lösung, gib genau das sofort und vollständig: Wortlaut, '
        'wahr oder falsch, Begründung mit Beleg. Das ist hier ausdrücklich erlaubt und hat Vorrang vor der Regel, Lösungen zurückzuhalten.\n'
        'Die Einordnungen unten sind aus den Kursunterlagen hergeleitet und keine offizielle Musterlösung; sag das einmal je Frage. '
        'Für diese Arbeit darfst du bis zu 450 Wörter schreiben.\n'
        f'Sind alle {count} Aussagen besprochen, fasse in zwei Sätzen zusammen und weise darauf hin, dass „nächste Aufgabe“ oder '
        '„Aufgabe N“ die Frage wechselt. Der Hub liefert dann die neue Frage; andere Fragen liegen dir jetzt nicht vor.\n'
        'Lernstand laut Hub: im Lernchat bereits geöffnet: '
        + (', '.join(f'Frage {item}' for item in selection['discussed']) or 'noch keine weitere Frage')
        + '; noch nicht geöffnet: ' + (', '.join(map(str, open_numbers)) or 'keine')
        + '. Der Hub merkt sich das selbst; sag bei Bedarf schlicht „Der Lernhub merkt sich, welche Fragen geöffnet wurden“, '
        'ohne über Schreibrechte zu sprechen, und werte „geöffnet“ nicht als „beherrscht“.\n\n')
    curated = _CuratedContext()
    curated.add(title, f"Aufgabenstellung: {question['prompt']}\nZu jeder der {count} Aussagen {letters} ist zu entscheiden, ob sie wahr ist.")
    for option in question['options']:
        curated.add(f"Aussage {option['id']}",
                    option['text'] + '\nHergeleitete Einordnung: ' + ('wahr' if option['is_correct'] else 'falsch')
                    + '\nBegründung: ' + option['explanation'], option['sources'])
    register = '\n\nBeigefügte Quellenbezüge (Originaltext nur soweit unten beigefügt):\n' + '\n'.join(
        f"[{ref['id']}] {ref['title']} · {_position(ref)}" + (f" · {ref['chapter']}" if ref.get('chapter') else '')
        for ref in curated.sources)
    base = lead + _DATA_NOTICE + ''.join(curated.parts) + register
    reminder = ('\n\nHinweis des Lernhubs (nicht Teil der Lerndaten): Belege fachliche Aussagen in deiner Antwort mit den '
                'passenden Quellen-IDs ' + ', '.join(f"[{ref['id']}]" for ref in curated.sources)
                + ' – jeweils nur, wenn die Aussage im Text genau dieser Quelle steht.') if curated.sources else ''
    limit = MAX_CONTEXT_CHARS if not max_chars else max(MIN_LOCAL_CONTEXT_CHARS, min(MAX_CONTEXT_CHARS, int(max_chars)))
    terms = _term_weights(''.join(curated.parts))
    excerpts, extracted, omitted, cut, unavailable, page_texts = _pdf_excerpts(
        curated.sources, project_root, source_root, max(0, limit - len(base) - len(_END) - len(reminder)), terms)
    notice = (f"Der Kontext enthält Frage {number} der {assignment['title']} mit hergeleiteten Einordnungen (keine offizielle Musterlösung)"
              + (f' und Textauszüge aus {extracted} belegten PDF-Seiten.' if extracted else '; aktuell ist kein Original-PDF-Text beigefügt.')
              + ' Der Hub merkt sich, welche Fragen im Lernchat geöffnet wurden; eine Bewertung speichert er dabei nicht.')
    if omitted or cut or curated.sources_omitted:
        notice += ' Belegstellen sind gekürzt oder nur teilweise beigefügt; die Links führen zum Original.'
    if unavailable:
        notice += ' Einzelne belegte PDF-Seiten sind nicht als Text verfügbar; dafür muss das verlinkte Original geprüft werden.'
    context_text = base + excerpts + _END + reminder
    spans = {key: [{'pdf_page': item['pdf_page'],
                    'start': _utf16_index(context_text, len(base) + item['start']),
                    'end': _utf16_index(context_text, len(base) + item['end'])} for item in items]
             for key, items in page_texts.items()}
    return {'module_id': module_id, 'title': _short(title, 360), 'context_text': context_text, 'sources': curated.sources,
            'suggestions': ['Erkläre mir zuerst den Stoff zu dieser Frage.', 'Lass mich Aussage A selbst einschätzen.',
                            'Nächste Aufgabe.'],
            'notice': notice, 'excerpts': spans, 'figures': [],
            # Reference data for the hub's own answer check; never sent to the browser.
            'check': {'opened': selection.get('opened', True),
                      'options': [{key: option[key] for key in ('id', 'text', 'is_correct')} for option in question['options']]},
            'assignment': {'id': assignment['id'], 'question': number, 'total': total}}
