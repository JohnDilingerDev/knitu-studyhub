import hashlib, time
from io import BytesIO
import pytest
from sqlalchemy import select
from test_private import env, login, B
from app import maintenance
from app.models import AuthSession, UsedLaunch

class Response(BytesIO):
    status = 200
    def geturl(self): return maintenance.SOURCE
class Opener:
    def __init__(self, value): self.value=value
    def open(self, request, timeout):
        assert request.full_url==maintenance.SOURCE and timeout==30
        return Response(self.value)

def test_fetch_fixed_source_and_size_limit():
    assert maintenance.fetch_schedule(Opener(b'{"sync":{"status":"ok"}}'))['sync']['status']=='ok'
    with pytest.raises(ValueError): maintenance.fetch_schedule(Opener(b'x'*(maintenance.MAX_BYTES+1)))
    with pytest.raises(ValueError): maintenance.fetch_schedule(Opener(b'[]'))
    with pytest.raises(ValueError): maintenance.NoRedirect().redirect_request(None,None,302,'',{},'https://example.org/')

def test_cleanup_preserves_live_session(env):
    c,sf=env
    live=login(c,100);expired=login(c,101)
    now=int(time.time())
    with sf.begin() as s:
        s.get(AuthSession,hashlib.sha256(expired['Authorization'].split()[1].encode()).hexdigest()).expires_at=now-1
        # create one expired launch without touching the actual launch tokens
        s.add(UsedLaunch(signature='0'*64,expires_at=now-1))
    with sf.begin() as s:
        assert maintenance.cleanup(s,now)=={'sessions':1,'launches':1}
    assert c.get('/api/v1/me',headers=live).status_code==200
    assert c.get('/api/v1/me',headers=expired).status_code==401
    with sf() as s: assert len(list(s.scalars(select(AuthSession))))==1
