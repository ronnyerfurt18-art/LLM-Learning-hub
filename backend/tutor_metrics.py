"""Measured values of one model request.

Only numbers the provider reports or the hub's own clock measures appear here.
A value without a measurement stays None; it is never estimated, and a missing
cache count is never read as zero or as a cache hit.
"""
from __future__ import annotations

import re
import math
import subprocess
import time

from .local_model import local_json

_SWAP_USED = re.compile(r'used = ([0-9.]+)M')


def _number(value):
    """A non-negative number, or None for anything else (bool, text, missing)."""
    return value if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) and value >= 0 else None


def _rate(tokens, seconds):
    return tokens / seconds if tokens and seconds else None


def _tokens(prompt, cached):
    """Total, reused and newly read prompt tokens; an implausible cache count is dropped."""
    if cached is not None and prompt is not None and cached > prompt:
        cached = None
    new = prompt - cached if prompt is not None and cached is not None else None
    return {'prompt_tokens': prompt, 'cached_tokens': cached, 'new_prompt_tokens': new,
            'cache_ratio': cached / prompt if cached is not None and prompt else None}


def ollama_stats(item):
    """Statistics of Ollama's final object (durations arrive in nanoseconds).

    prompt_eval_count is the whole prompt including the reused part and
    prompt_eval_duration covers only the newly read tokens (checked with Ollama 0.35.0).
    """
    item = item if isinstance(item, dict) else {}
    seconds = {key: None if _number(item.get(key)) is None else item[key] / 1e9
               for key in ('load_duration', 'prompt_eval_duration', 'eval_duration')}
    tokens = _tokens(_number(item.get('prompt_eval_count')), _number(item.get('prompt_eval_cached_count')))
    output = _number(item.get('eval_count'))
    # Without a cache count the share of new tokens is unknown, and so is the reading speed.
    read = tokens['new_prompt_tokens']
    return {**tokens, 'load_seconds': seconds['load_duration'],
            'prefill_seconds': seconds['prompt_eval_duration'],
            'prefill_tokens_per_second': _rate(read, seconds['prompt_eval_duration']),
            'output_tokens': output, 'decode_seconds': seconds['eval_duration'],
            'decode_tokens_per_second': _rate(output, seconds['eval_duration']), 'peak_memory_bytes': None}


def bonsai_stats(usage, timings):
    """Statistics of the Bonsai runtime (mlx-vlm): OpenAI usage plus its own timings object.

    The runtime reports no model load time. Its prompt_ms is derived from the whole
    prompt, so the reading time is only passed on when nothing came from the cache.
    """
    usage = usage if isinstance(usage, dict) else {}
    timings = timings if isinstance(timings, dict) else {}
    details = usage.get('prompt_tokens_details')
    cached = _number(details.get('cached_tokens')) if isinstance(details, dict) else None
    if cached is None:
        cached = _number(timings.get('cache_n'))
    tokens = _tokens(_number(usage.get('prompt_tokens')), cached)
    output = _number(usage.get('completion_tokens'))
    if output is None:
        output = _number(timings.get('predicted_n'))
    prompt_ms, predicted_ms = _number(timings.get('prompt_ms')), _number(timings.get('predicted_ms'))
    prefill = prompt_ms / 1000 if prompt_ms and tokens['cached_tokens'] == 0 else None
    peak = _number(timings.get('peak_memory'))
    return {**tokens, 'load_seconds': None, 'prefill_seconds': prefill,
            'prefill_tokens_per_second': (_number(timings.get('prompt_per_second')) or None)
            if tokens['cached_tokens'] == 0 else None,
            'output_tokens': output, 'decode_seconds': predicted_ms / 1000 if predicted_ms else None,
            'decode_tokens_per_second': _number(timings.get('predicted_per_second')) or None,
            # Installed mlx-vlm uses mx.get_peak_memory() / 1e9 (decimal GB).
            'peak_memory_bytes': int(peak * 1e9) if peak else None}


def _sysctl(names):
    return subprocess.run(['/usr/sbin/sysctl', '-n', *names], capture_output=True, text=True, timeout=2).stdout


def memory_snapshot(provider, model, request=local_json, sysctl=_sysctl):
    """Memory held by the model and the system's memory pressure (macOS); unknown values stay None."""
    result = {'model_bytes': None, 'pressure_level': None, 'swap_used_bytes': None}
    if provider == 'ollama':
        try:
            loaded = next((item for item in request('/api/ps').get('models', [])
                           if isinstance(item, dict) and item.get('name') == model), None)
            result['model_bytes'] = _number(loaded.get('size')) if loaded else None
        except Exception:
            pass
    try:
        # 1 normal, 2 warning, 4 critical.
        level = sysctl(['kern.memorystatus_vm_pressure_level']).strip()
        result['pressure_level'] = int(level) if level in ('1', '2', '4') else None
        swap = _SWAP_USED.search(sysctl(['vm.swapusage']))
        result['swap_used_bytes'] = int(float(swap.group(1)) * 1024 * 1024) if swap else None
    except Exception:
        pass
    return result


class Stopwatch:
    """The hub's own clock for one request: sent, first token, first visible text, finished."""

    def __init__(self, clock=time.perf_counter):
        self._clock = clock
        self.started = clock()
        self.first_token = self.first_visible = None

    def token(self, visible):
        now = self._clock() - self.started
        if self.first_token is None:
            self.first_token = now
        if visible and self.first_visible is None:
            self.first_visible = now

    def elapsed(self):
        return self._clock() - self.started


def performance(provider, model, watch, stats, memory=None, context_seconds=None):
    """One flat record for the done event; keys are stable, unknown values are None."""
    memory = dict(memory or {})
    if stats.get('peak_memory_bytes') is not None:
        memory['peak_bytes'] = stats['peak_memory_bytes']
    return {'provider': provider, 'model': model,
            # Seconds since the service clock started before its model check; excludes context building.
            'first_token_seconds': watch.first_token, 'ttft_seconds': watch.first_visible,
            'total_seconds': watch.elapsed(), 'context_seconds': context_seconds,
            **{key: value for key, value in stats.items() if key != 'peak_memory_bytes'},
            'memory': memory}
