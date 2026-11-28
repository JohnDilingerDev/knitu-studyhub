from test_private import env, login, B

def test_cabinet_assets(env):
    c,_=env
    assert c.get('/',follow_redirects=False).headers['location']=='/cabinet/'
    r=c.get('/cabinet/');assert r.status_code==200
    assert 'https://st.max.ru/js/max-web-app.js' in r.text
    assert r.headers['cache-control']=='no-store'
    assert "script-src 'self' https://st.max.ru" in r.headers['content-security-policy']
    js=c.get('/cabinet/app.js');assert js.status_code==200
    assert 'initDataUnsafe' not in js.text and 'localStorage.setItem(storageKey()' in js.text
    assert c.get('/cabinet/style.css').status_code==200
    assert c.get('/cabinet/.env').status_code==404

def test_import_only_missing(env):
    c,_=env;h=login(c,100);other=login(c,101)
    assert c.put(B+'/me/progress/P01',headers=h,json={'status':'checked'}).status_code==200
    assert c.put(B+'/me/digit',headers=h,json={'digit':0}).status_code==200
    body={'progress':{'P01':'prepared','P02':'submitted','fake':'accepted'},'digit':2}
    r=c.post(B+'/me/import',headers=h,json=body);assert r.status_code==200,r.text
    assert r.json()=={'progress':{'P01':'checked','P02':'submitted'},'digit':0,'added':1}
    assert c.post(B+'/me/import',headers=h,json=body).json()['added']==0
    assert c.get(B+'/me/progress',headers=other).json()['progress']=={}
    assert c.post(B+'/me/import',json=body).status_code==401
    assert c.post(B+'/me/import',headers=h,json={'progress':{'P01':'fake'}}).status_code==422
