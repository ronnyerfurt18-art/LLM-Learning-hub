import argparse
from datetime import datetime, timedelta, timezone
import json
from unittest.mock import Mock

import pytest
from tools import overnight_tutor_benchmark as night


def runner(tmp_path):
    suite = tmp_path / 'suite.json'
    suite.write_text(json.dumps({'questions': [], 'rubric': {}}))
    return night.NightRun(argparse.Namespace(suite=suite, output=tmp_path,
        not_before=datetime.now(timezone.utc), deadline=datetime.now(timezone.utc) + timedelta(hours=1), cooldown=0))


def test_only_complete_answers_are_resumed():
    row = {'type': 'result', 'model': 'qwen', 'question_id': 'q1', 'repetition': 1, 'answer': 'Antwort'}
    assert night.completed([row, {**row, 'repetition': 2, 'error': 'failed'},
                            {**row, 'repetition': 3, 'answer': ''}]) == {('qwen', 'q1', 1)}


def test_jsonl_roundtrip_and_partial_data_is_preserved(tmp_path):
    path = tmp_path / 'results.jsonl'
    night.append(path, {'answer': 'Überprüfung'})
    assert night.records(path) == [{'answer': 'Überprüfung'}]
    broken = path.read_bytes() + b'{"answer":'
    path.write_bytes(broken)
    with pytest.raises(RuntimeError, match='Incomplete JSONL'):
        night.records(path)
    assert path.read_bytes() == broken


@pytest.mark.parametrize('models,in_flight', [([{'name': 'qwen'}], 0), ([], 1)])
def test_shared_activity_prevents_unload(tmp_path, monkeypatch, models, in_flight):
    run = runner(tmp_path)
    monkeypatch.setattr(night, 'get', lambda url: {'models': models} if url.endswith('/api/ps') else
                        {'summary': {'in_flight': in_flight}})
    post = Mock()
    monkeypatch.setattr(night.bench, 'post', post)
    with pytest.raises(RuntimeError, match='another|Another'):
        run.unload()
    post.assert_not_called()


def test_new_external_request_prevents_unload(tmp_path, monkeypatch):
    run = runner(tmp_path)
    run.owned_ollama = 'qwen'
    run.expected_expiry = 'old'
    monkeypatch.setattr(night, 'get', lambda url: {'models': [{'name': 'qwen', 'expires_at': 'new'}]})
    post = Mock()
    monkeypatch.setattr(night.bench, 'post', post)
    with pytest.raises(RuntimeError, match='changed model activity'):
        run.unload()
    post.assert_not_called()


def test_deadline_stops_new_work(tmp_path):
    run = runner(tmp_path)
    run.args.deadline = datetime.now(timezone.utc) - timedelta(seconds=1)
    with pytest.raises(TimeoutError):
        run.assert_exclusive()


def test_summary_does_not_invent_quality_scores(tmp_path):
    run = runner(tmp_path)
    run.report('scheduled')
    status = json.loads((tmp_path / 'status.json').read_text())
    assert status['completed_responses'] == 0
    assert status['quality_review'].startswith('pending')
    assert not (tmp_path / 'blinded-review.json').exists()


def test_hub_verification_preserves_another_selected_provider(tmp_path, monkeypatch):
    run = runner(tmp_path)
    monkeypatch.setattr(night, 'get', lambda url: {'provider': 'ollama'})
    post = Mock()
    monkeypatch.setattr(night.bench, 'post', post)
    run.hub_smoke()
    post.assert_not_called()
    assert not (tmp_path / 'hub-smoke.json').exists()


def test_hub_verification_requires_a_finished_answer_and_metrics(tmp_path, monkeypatch):
    import io
    run = runner(tmp_path)
    run.suite['questions'] = [{'request': {'message': 'Frage'}}]
    run.wait_for_idle = Mock()
    monkeypatch.setattr(night, 'get', lambda url: {'summary': {'last_request_at': 1}} if url.endswith('/metrics')
                        else {'provider': 'bonsai', 'readiness': 'ready'})
    final = {'type': 'done', 'answer': 'Antwort', 'performance': {'first_token_seconds': 1}}
    post = Mock(side_effect=[io.BytesIO(b'{}'), io.BytesIO(json.dumps(final).encode() + b'\n')])
    monkeypatch.setattr(night.bench, 'post', post)
    run.hub_smoke()
    assert json.loads((tmp_path / 'hub-smoke.json').read_text()) == final
    assert run.owned_bonsai
