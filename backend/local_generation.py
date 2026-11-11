"""Shared plumbing for everything the local model drafts (module import, big picture)."""
import json

from .local_model import CONTEXT_TOKENS, KEEP_ALIVE, local_json, local_model_info

OUTPUT_TOKENS = 6000
REQUEST_TIMEOUT = 1200


def parse_json(text):
    """Model answer as an object; tolerates code fences and stray text around it."""
    if not isinstance(text, str):
        raise ValueError('Keine Textantwort.')
    start, end = text.find('{'), text.rfind('}')
    if start < 0 or end <= start:
        raise ValueError('Kein JSON-Objekt in der Antwort.')
    value = json.loads(text[start:end + 1])
    if not isinstance(value, dict):
        raise ValueError('Antwort ist kein JSON-Objekt.')
    return value


def ollama_generator(model, request=local_json, schema=None, output_tokens=OUTPUT_TOKENS):
    """One bounded local call per prompt. Raises ValueError if the model is not usable.

    `schema` is the JSON schema for structured output; callers pass the one of their own task.
    """
    info = local_model_info(model, request)
    thinking = 'thinking' in info.get('capabilities', [])

    def generate(messages, structured=True):
        payload = {'model': model, 'messages': messages, 'stream': False, 'keep_alive': KEEP_ALIVE,
                   'options': {'num_ctx': CONTEXT_TOKENS, 'num_predict': output_tokens, 'temperature': 0.2}}
        if structured and schema is not None:
            payload['format'] = schema
        if thinking:
            payload['think'] = False
        result = request('/api/chat', payload, timeout=REQUEST_TIMEOUT)
        return parse_json((result.get('message') or {}).get('content'))
    return generate
