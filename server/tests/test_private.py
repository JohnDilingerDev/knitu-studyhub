import hashlib,hmac,json,time,uuid,os
from urllib.parse import urlencode
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select,func
from app.models import Base,User,Group,Membership,AuthSession,AuditEvent
from app.db import make_engine,session_factory
from app.import_data import import_bundle,load_json,SLUG
from app.main import create_app
from app.max_auth import verify_launch,InvalidLaunch

ROOT=Path(__file__).resolve().parents[1]
TOKEN='synthetic-ci-only-token-never-use-in-production'
B='/api/v1/groups/'+SLUG

def signed(uid=100,stamp=None,token=TOKEN,**extra):
    fields={'user':json.dumps({'id':uid,'first_name':'Тест + &'},ensure_ascii=False),'auth_date':str(int(time.time()) if stamp is None else stamp),'query_id':str(uuid.uuid4()),**extra}
    secret=hmac.new(b'WebAppData',token.encode(),hashlib.sha256).digest()
    fields['hash']=hmac.new(secret,'\n'.join(f'{k}={v}' for k,v in sorted(fields.items())).encode(),hashlib.sha256).hexdigest()
    return urlencode(fields)

@pytest.fixture
def env(tmp_path,monkeypatch):
    monkeypatch.setenv('MAX_BOT_TOKEN',TOKEN)
    # Optional CI integration: only use the dedicated disposable database.
    url=os.environ.get('STUDYHUB_PRIVATE_TEST_DB') or 'sqlite:///'+str(tmp_path/'auth.sqlite')
    engine=make_engine(url)
    if os.environ.get("STUDYHUB_PRIVATE_TEST_DB") and engine.url.database!="studyhub_private_ci":
        raise RuntimeError("Refusing to run destructive tests outside dedicated CI database")
    Base.metadata.create_all(engine);sf=session_factory(engine)
    with sf.begin() as s:
        import_bundle(s,load_json(ROOT/'seed/data.json'),load_json(ROOT/'seed/content.json'))
        g=s.scalar(select(Group));other=Group(university_id=g.university_id,slug='other',code='OTHER',term=g.term,public=False);s.add(other);s.flush()
        for uid,role,owner,active in [(100,'student',False,True),(101,'student',False,True),(102,'admin',False,True),(103,'admin',True,True),(104,'student',False,False)]:
            u=User(max_user_id=uid,owner=owner,active=active);s.add(u);s.flush();s.add(Membership(group_id=g.id,user_id=u.id,role=role))
    try:
        with TestClient(create_app(engine)) as c: yield c,sf
    finally:
        # Only the dedicated disposable CI database is dropped.
        if os.environ.get("STUDYHUB_PRIVATE_TEST_DB"): Base.metadata.drop_all(engine)
        engine.dispose()

def login(c,uid):
    r=c.post('/api/v1/auth/max',json={'init_data':signed(uid)});assert r.status_code==200,r.text
    return {'Authorization':'Bearer '+r.json()['access_token']}

def task(**kw): return dict(subject='ИПП',title='Тест задания',description='Требования',source='Тестовый источник',deadline='2026-12-02',show_deadline=True,**kw)

def test_signature_and_freshness():
    now=1800000000
    raw=signed(stamp=now)
    assert verify_launch(raw,TOKEN,now)[0]==100
    for bad in [raw.replace('100','999',1),raw+'&hash='+'0'*64,raw+'&user=x',signed(stamp=now-301),signed(stamp=now+31),signed(stamp=now,token='wrong'),signed(uid=True,stamp=now),'%ZZ=x']:
        with pytest.raises(InvalidLaunch): verify_launch(bad,TOKEN,now)

def test_login_replay_logout(env):
    c,sf=env;raw=signed();r=c.post('/api/v1/auth/max',json={'init_data':raw});assert r.status_code==200
    assert r.headers['cache-control']=='no-store'
    token=r.json()['access_token'];h={'Authorization':'Bearer '+token}
    with sf() as s:
        assert s.scalar(select(AuthSession)).token_hash==hashlib.sha256(token.encode()).hexdigest()
    assert c.post('/api/v1/auth/max',json={'init_data':raw}).status_code==401
    assert c.get('/api/v1/me',headers=h).json()['owner'] is False
    assert c.post('/api/v1/auth/logout',headers=h).status_code==200
    assert c.get('/api/v1/me',headers=h).status_code==401

def test_denials(env,monkeypatch):
    c,sf=env
    for uid in (104,999): assert c.post('/api/v1/auth/max',json={'init_data':signed(uid)}).status_code==403
    assert c.post('/api/v1/auth/max',json={'init_data':signed(),'role':'owner'}).status_code==422
    assert c.get('/api/v1/me').status_code==401
    assert c.get('/api/v1/me',headers={'Authorization':'Bearer fake'}).status_code==401
    h=login(c,100)
    with sf.begin() as s: s.scalar(select(AuthSession)).expires_at=0
    assert c.get('/api/v1/me',headers=h).status_code==401
    h=login(c,100)
    with sf.begin() as s: s.scalar(select(User).where(User.max_user_id==100)).active=False
    assert c.get('/api/v1/me',headers=h).status_code==401
    monkeypatch.delenv('MAX_BOT_TOKEN');assert c.post('/api/v1/auth/max',json={'init_data':signed()}).status_code==503

def test_progress_isolation(env):
    c,_=env;a=login(c,100);b=login(c,101);admin=login(c,102)
    assert c.put(B+'/me/progress/P01',headers=a,json={'status':'prepared'}).status_code==200
    assert c.put(B+'/me/progress/P01',headers=a,json={'status':'checked'}).status_code==200
    assert c.put(B+'/me/digit',headers=a,json={'digit':0}).status_code==200
    assert c.get(B+'/me/progress',headers=a).json()=={'digit':0,'progress':{'P01':'checked'}}
    for h in (b,admin): assert c.get(B+'/me/progress',headers=h).json()['progress']=={}
    assert c.put(B+'/me/progress/P01',headers=b,json={'status':'prepared','user_id':100}).status_code==422
    assert c.get('/api/v1/groups/other/me/progress',headers=a).status_code==403
    assert c.put(B+'/me/progress/unknown',headers=a,json={'status':'prepared'}).status_code==404

def test_admin_write_and_audit(env):
    c,sf=env;student=login(c,100);admin=login(c,102)
    assert c.post(B+'/admin/tasks',json=task(),headers=student).status_code==403
    assert c.post('/api/v1/groups/other/admin/tasks',json=task(),headers=admin).status_code==403
    r=c.post(B+'/admin/tasks',json=task(),headers=admin);assert r.status_code==201,r.text;code=r.json()['id']
    assert c.put(B+'/admin/tasks/'+code,json={**task(),'title':'Исправлено'},headers=admin).status_code==200
    r=c.post(B+'/admin/announcements',json={'date':'2026-11-27','title':'Новость','body':'Текст','source':'Источник'},headers=admin);assert r.status_code==201,r.text
    assert c.put(B+'/admin/announcements/'+r.json()['id'],json={'date':'2026-11-27','title':'Обновлено','body':'Текст','source':'Источник'},headers=admin).status_code==200
    bundle=c.get(B+'/bundle').json();assert any(t['id']==code and t['title']=='Исправлено' for t in bundle['tasks']);assert any(code in d['task_ids'] for d in bundle['deadlines']);assert bundle['announcements'][-1]['title']=='Обновлено'
    assert c.get(B+'/admin/audit',headers=student).status_code==403
    audit=c.get(B+'/admin/audit',headers=admin).json();assert len(audit)==4;assert audit[0]['details']['after']['title']=='Обновлено'
    assert c.post(B+'/admin/tasks',json={**task(),'subject':'wrong'},headers=admin).status_code==422
    with sf() as s: assert s.scalar(select(func.count()).select_from(AuditEvent))==4

def test_verified_schedule_preserves_admin_content(env):
    from copy import deepcopy
    import datetime as dt
    from app.sync_schedule import sync_schedule
    c,sf=env;admin=login(c,102)
    r=c.post(B+'/admin/tasks',json=task(),headers=admin);assert r.status_code==201
    code=r.json()['id'];data=load_json(ROOT/'seed/data.json');content=load_json(ROOT/'seed/content.json')
    now=dt.datetime.now(dt.timezone.utc)
    data['sync']={'checked_at':now.isoformat(),'status':'ok','coverage_end':data['schedule']['end']}
    data['schedule']['entries'][0]['Room']='TEST-ROOM'
    with sf.begin() as s: assert sync_schedule(s,data,now)==49
    bundle=c.get(B+'/bundle').json();assert bundle['schedule']['entries'][0]['Room']=='TEST-ROOM';assert any(t['id']==code for t in bundle['tasks'])
    assert bundle['sync']['status']=='ok'
    failed=deepcopy(data);failed['sync']['status']='failed'
    with pytest.raises(ValueError),sf.begin() as s: sync_schedule(s,failed,now)
    stale=deepcopy(data);stale['sync']['checked_at']=(now-dt.timedelta(days=1)).isoformat()
    with pytest.raises(ValueError),sf.begin() as s: sync_schedule(s,stale,now)
    with pytest.raises(ValueError),sf.begin() as s: import_bundle(s,data,content)
    assert c.get(B+'/bundle').json()==bundle
