import io
import json
from unittest.mock import patch

import pytest

from tools import bench_tutor_models as bench


def test_ollama_cache_speed_uses_new_tokens_and_requires_final():
    stream = io.BytesIO(b'\n'.join(json.dumps(item).encode() for item in [
        {'message': {'thinking': 'Think'}}, {'message': {'content': 'Answer'}},
        {'done': True, 'done_reason': 'stop', 'prompt_eval_count': 100,
         'prompt_eval_cached_count': 90, 'prompt_eval_duration': 2000000000}]))
    with patch.object(bench, 'post', return_value=stream), patch.object(bench, 'memory_snapshot', return_value={}):
        result = bench.run_ollama('test', [], 50)
    assert result['prefill_tps'] == 5
    assert result['first'] >= result['performance']['first_token_seconds']
    assert result['out_tokens'] is None
    with patch.object(bench, 'post', return_value=io.BytesIO(b'{"message":{"content":"partial"}}\n')):
        with pytest.raises(RuntimeError, match='without completion'):
            bench.run_ollama('test', [], 50)


def test_bonsai_never_counts_chunks_as_tokens_or_ttft_as_prefill():
    stream = io.BytesIO(b'data: {"choices":[{"delta":{"content":"Answer"},"finish_reason":"stop"}]}\n'
                        b'data: [DONE]\n')
    with patch.object(bench, 'post', return_value=stream), patch.object(bench, 'memory_snapshot', return_value={}):
        result = bench.run_bonsai([], 50)
    for key in ('out_tokens', 'prompt_tokens', 'prefill_tps', 'decode_tps', 'load'):
        assert result[key] is None
    assert result['first'] is not None


def test_suite_persists_failure_and_does_not_claim_success(tmp_path):
    from argparse import Namespace
    suite = tmp_path / 'suite.json'
    suite.write_text(json.dumps({'questions': [{'id': 'q1', 'category': 'knowledge', 'messages': []}]}))
    output = tmp_path / 'result.jsonl'
    args = Namespace(suite=str(suite), output=str(output), provider='ollama', model='test', cold=False,
                     repeat=2, max_tokens=50, cooldown=0)
    with patch.object(bench, 'run_ollama', side_effect=OSError('offline')), patch.object(bench, 'thermal_snapshot', return_value=None):
        with pytest.raises(OSError, match='offline'):
            bench.run_suite(args)
    rows = [json.loads(line) for line in output.read_text().splitlines()]
    assert rows[0]['type'] == 'manifest'
    assert rows[1]['status'] == 'failed'
    assert rows[1]['quality_review'] is None
    assert 'first' not in rows[1]
    with pytest.raises(FileExistsError):
        bench.run_suite(args)
