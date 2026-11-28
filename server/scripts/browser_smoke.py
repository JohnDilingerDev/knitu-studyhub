"""Disposable mobile-browser smoke test. Never uses production database or real MAX credentials."""
import os,sys,time,subprocess,tempfile,hashlib,hmac,json,uuid
from urllib.parse import urlencode
from playwright.sync_api import sync_playwright
from app.db import make_engine,session_factory
from app.models import Base,User,Group,Membership
from app.import_data import import_bundle,load_json
from sqlalchemy import select
TOKEN='synthetic-browser-only-test-token'
with tempfile.TemporaryDirectory() as d:
 url='sqlite:///'+d+'/test.sqlite'; e=make_engine(url);Base.metadata.create_all(e);sf=session_factory(e)
 with sf.begin() as s:
  import_bundle(s,load_json('seed/data.json'),load_json('seed/content.json'));g=s.scalar(select(Group));u=User(max_user_id=500,owner=True,active=True);s.add(u);s.flush();s.add(Membership(group_id=g.id,user_id=u.id,role='admin'))
 e.dispose(); proc=subprocess.Popen([sys.executable,'-m','uvicorn','app.main:app','--host','127.0.0.1','--port','8765'],env={**os.environ,'DATABASE_URL':url,'MAX_BOT_TOKEN':TOKEN},stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
 try:
  import httpx
  for _ in range(50):
   try:
    if httpx.get('http://127.0.0.1:8765/health').status_code==200:break
   except Exception:time.sleep(.1)
  fields={'user':json.dumps({'id':500}),'auth_date':str(int(time.time())),'query_id':str(uuid.uuid4())};key=hmac.new(b'WebAppData',TOKEN.encode(),hashlib.sha256).digest();fields['hash']=hmac.new(key,'\n'.join(f'{k}={v}' for k,v in sorted(fields.items())).encode(),hashlib.sha256).hexdigest();raw=urlencode(fields)
  with sync_playwright() as p:
   b=p.chromium.launch(headless=True,args=['--no-sandbox','--disable-dev-shm-usage']);page=b.new_page(viewport={'width':390,'height':844});errors=[];page.on('pageerror',lambda err:errors.append(str(err)));page.route('https://st.max.ru/js/max-web-app.js',lambda route:route.fulfill(content_type='application/javascript',body='window.WebApp={initData:'+json.dumps(raw)+'};'));page.on('dialog',lambda dialog:dialog.accept());page.goto('http://127.0.0.1:8765/cabinet/');page.get_by_role('heading',name='Учебный кабинет',exact=True).wait_for();page.get_by_role('button',name='Расписание',exact=True).click();
   with page.expect_download() as download: page.get_by_role('button',name='Экспорт всего расписания (.ics)').click()
   assert download.value.suggested_filename.endswith('.ics')
   assert open(download.value.path(),encoding='utf-8').read().count('BEGIN:VEVENT')==49
   page.get_by_role('button',name='Задания',exact=True).click();page.get_by_label('Статус: Спиртовое брожение').select_option('prepared');page.get_by_text('Отметка сохранена',exact=True).wait_for();page.get_by_role('button',name='Войти через MAX').click();page.get_by_text('Владелец',exact=True).wait_for();page.get_by_role('button',name='Настройки',exact=True).click();page.get_by_role('button',name='Перенести гостевые отметки').click();page.get_by_text('Добавлено отметок: 1',exact=True).wait_for();page.get_by_role('button',name='Задания',exact=True).click();assert page.get_by_label('Статус: Спиртовое брожение').input_value()=='prepared';page.get_by_role('button',name='Управление',exact=True).click();page.get_by_label('Название',exact=True).fill('Проверка интерфейса');page.get_by_label('Требования',exact=True).fill('Тестовый текст');page.get_by_label('Источник',exact=True).first.fill('Тест');page.get_by_role('button',name='Опубликовать задание').click();page.get_by_text('Задание опубликовано',exact=True).wait_for();page.get_by_role('button',name='Выйти',exact=True).click();page.get_by_text('Гостевой режим',exact=True).wait_for();assert not page.get_by_role('button',name='Управление',exact=True).count();assert not errors,errors;print('Mobile Chromium smoke: PASSED');b.close()
 finally:proc.terminate();proc.wait(timeout=10)
