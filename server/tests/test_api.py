from pathlib import Path
from copy import deepcopy
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select,func
from sqlalchemy.exc import IntegrityError
from app.db import make_engine,session_factory
from app.models import Base,Group,User,Membership,Progress,Task,ScheduleEntry
from app.import_data import import_bundle,load_json,SLUG
from app.main import create_app
from app.auth import may_edit_group,may_access_progress

ROOT=Path(__file__).resolve().parents[1]
DATA=load_json(ROOT/'seed/data.json');CONTENT=load_json(ROOT/'seed/content.json')
@pytest.fixture
def db(tmp_path):
    engine=make_engine('sqlite:///'+str(tmp_path/'test.sqlite'));Base.metadata.create_all(engine);sf=session_factory(engine)
    with sf.begin() as s: import_bundle(s,DATA,CONTENT)
    yield engine,sf
    engine.dispose()

def test_exact_import_and_bundle(db):
    e,sf=db
    with TestClient(create_app(e)) as c:
        r=c.get('/api/v1/groups/'+SLUG+'/bundle');assert r.status_code==200
        d=r.json();assert d['schedule']==DATA['schedule'];assert d['variants']==DATA['variants'];assert d['tasks']==CONTENT['tasks'];assert d['announcements']==CONTENT['announcements'];assert d['deadlines']==CONTENT['deadlines']
        assert len(d['schedule']['entries'])==49;assert len(d['tasks'])==38
        assert c.get('/health').json()['status']=='ok'

def test_all_variants(db):
    with TestClient(create_app(db[0])) as c:
        for digit in range(10):
            v=c.get(f'/api/v1/groups/{SLUG}/variants/{digit}').json();n=digit or 10
            assert v['variant']==n and [x['topic'] for x in v['tasks']]==[row[n-1] for row in DATA['variants']]
        assert c.get(f'/api/v1/groups/{SLUG}/variants/11').status_code==422

def test_schedule_filters(db):
    with TestClient(create_app(db[0])) as c:
        r=c.get(f'/api/v1/groups/{SLUG}/schedule',params={'start':'2026-11-25','end':'2026-11-25'})
        assert len(r.json()['entries'])==3
        assert c.get(f'/api/v1/groups/{SLUG}/schedule',params={'start':'2027-01-01','end':'2026-12-01'}).status_code==422

def test_private_group_and_auth_disabled(db):
    e,sf=db
    with sf.begin() as s:
        g=s.scalar(select(Group));s.add(Group(university_id=g.university_id,slug='private',code='TEST',term=g.term,public=False))
    with TestClient(create_app(e)) as c:
        assert len(c.get('/api/v1/groups').json())==1
        assert c.get('/api/v1/groups/private/bundle').status_code==404
        assert c.post('/api/v1/auth/max',json={'user_id':123,'role':'owner'}).status_code==503
        assert c.post(f'/api/v1/groups/{SLUG}/tasks',json={'title':'fake'}).status_code==405

def test_repeat_import_and_progress_preserved(db):
    _,sf=db
    with sf.begin() as s:
        g=s.scalar(select(Group));u=User(max_user_id=1);s.add(u);s.flush();s.add(Membership(group_id=g.id,user_id=u.id,role='student'));s.flush();s.add(Progress(group_id=g.id,user_id=u.id,task_code='P01',status='prepared'))
    with sf.begin() as s: import_bundle(s,DATA,CONTENT)
    with sf.begin() as s:
        assert s.scalar(select(func.count()).select_from(Task))==38
        assert s.scalar(select(func.count()).select_from(ScheduleEntry))==49
        assert s.scalar(select(Progress)).status=='prepared'
        changed=deepcopy(CONTENT);changed['tasks']=[t for t in changed['tasks'] if t['id']!='P01']
        for d in changed['deadlines']: d['task_ids']=[x for x in d['task_ids'] if x!='P01']
        import_bundle(s,DATA,changed)
    with sf.begin() as s:
        assert s.scalar(select(Task).where(Task.code=='P01')).active is False
        assert s.scalar(select(Progress)).status=='prepared'

def test_role_isolation(db):
    _,sf=db
    with sf.begin() as s:
        g=s.scalar(select(Group));other=Group(university_id=g.university_id,slug='other',code='OTHER',term=g.term,public=True);s.add(other)
        student=User(max_user_id=1);admin=User(max_user_id=2);owner=User(max_user_id=3,owner=True);disabled=User(max_user_id=4,active=False,owner=True);s.add_all([student,admin,owner,disabled]);s.flush()
        s.add_all([Membership(group_id=g.id,user_id=student.id,role='student'),Membership(group_id=g.id,user_id=admin.id,role='admin')]);s.flush()
        assert not may_edit_group(s,student.id,g.id);assert may_edit_group(s,admin.id,g.id);assert not may_edit_group(s,admin.id,other.id);assert may_edit_group(s,owner.id,other.id);assert not may_edit_group(s,disabled.id,g.id)
        assert may_access_progress(s,student.id,student.id,g.id);assert not may_access_progress(s,admin.id,student.id,g.id)
        with pytest.raises(IntegrityError),s.begin_nested():
            s.add(Progress(group_id=other.id,user_id=student.id,task_code='P01',status='prepared'));s.flush()

def test_wrong_group_import_is_atomic(db):
    _,sf=db
    bad=deepcopy(CONTENT);bad['group']='other'
    with pytest.raises(ValueError),sf.begin() as s: import_bundle(s,DATA,bad)
    with sf.begin() as s: assert s.scalar(select(func.count()).select_from(Task))==38
