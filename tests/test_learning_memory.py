import json
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from backend.core import Hub
from backend.learning_memory import LearningMemory

def setup(tmp_path):
    (tmp_path/'content/tutor').mkdir(parents=True)
    (tmp_path/'content/tutor/goals.json').write_text(json.dumps([{'id':'g','module_id':'m','title':'Goal'}]))
    return LearningMemory(Hub(tmp_path/'test.sqlite3'), tmp_path)

def event(outcome='independent', **kw):
    return dict(id=str(uuid.uuid4()),module_id='m',goal_id='g',outcome=outcome,answer='Eigene Erklärung',without_help=True,**kw)

def test_persistence_spacing_and_undo(tmp_path):
    m=setup(tmp_path); at=datetime(2026,1,1,tzinfo=timezone.utc)
    first=event(); m.record(first,at)
    second=event(); m.record(second,at+timedelta(hours=2))
    state=m.state(m.goals[0],at)
    assert state['status']=='independent'
    assert state['next_due']==(at+timedelta(days=1)).isoformat()
    later=event(); m.record(later,at+timedelta(days=2))
    assert m.state(m.goals[0])['status']=='confirmed'
    restarted=LearningMemory(Hub(tmp_path/'test.sqlite3'),tmp_path)
    assert restarted.state(m.goals[0])['status']=='confirmed'
    restarted.undo('m','g',later['id'])
    state=restarted.state(m.goals[0])
    assert state['status']=='independent'
    assert len(state['events'])==3 and state['events'][-1]['voided']==1

def test_help_resets_success_and_repeat_is_idempotent(tmp_path):
    m=setup(tmp_path);at=datetime(2026,1,1,tzinfo=timezone.utc)
    e=event();m.record(e,at);m.record(e,at)
    assert len(m.state(m.goals[0])['events'])==1
    m.record(event('helped'),at+timedelta(days=2))
    state=m.state(m.goals[0],at+timedelta(days=2,minutes=11))
    assert state['status']=='helped' and state['due']
    m.record(event(),at+timedelta(days=3))
    assert m.state(m.goals[0])['status']=='independent'

def test_no_automatic_promotion_and_scope_validation(tmp_path):
    import pytest
    m=setup(tmp_path)
    e=event();e['module_id']='another'
    with pytest.raises(ValueError):m.record(e)
    e=event();e['without_help']=False
    with pytest.raises(ValueError):m.record(e)
    e=event();e['answer']=''
    with pytest.raises(ValueError):m.record(e)
    m.record(event('unclear'))
    assert m.state(m.goals[0])['status']=='unclear'


def test_goal_catalog_is_not_loaded_as_learning_package(tmp_path):
    from backend.learning_pages import load_learning_pages
    memory = setup(tmp_path)
    assert len(memory.goals) == 1
    packages, errors = load_learning_pages(tmp_path, tmp_path)
    assert packages == [] and errors == []
    (tmp_path/'content/broken.json').write_text('[]')
    _, errors = load_learning_pages(tmp_path, tmp_path)
    assert len(errors) == 1  # Actual malformed learning packages still fail.
