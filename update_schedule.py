#!/usr/bin/env python3
"""StudyHub: verify the entire current semester snapshot before replacing it."""
import argparse, datetime as dt, html, json, pathlib, re, shutil, sys, time
from collections import Counter
from urllib.request import Request, urlopen

ROOT=pathlib.Path(__file__).resolve().parent
MSK=dt.timezone(dt.timedelta(hours=3))
GROUP='661-М52 ИППБТ'
START=dt.date(2026,11,23); END=dt.date(2027,1,24); EXAM=dt.date(2027,1,11)
FIELDS=('Date','Start','End','Pair','Subject','Type','Teacher','Room','Period','Subgroup','Details','Source','Category')
ASSETS=('index.html','manifest.webmanifest','sw.js','icon-192.png','icon-512.png','admin.html','content.json')

def clean(s): return ' '.join(html.unescape(re.sub(r'<[^>]+>',' ',s)).split())
def matches(pattern,s): return re.findall(pattern,s,re.I|re.S)
def table(s):
    if not re.search(r'<title[^>]*>[^<]*661\s*[-–]\s*[МM]52',s,re.I|re.S): raise ValueError('wrong group/title')
    m=re.search(r'<table\b[^>]*class\s*=\s*["\'][^"\']*\bbrstu-table\b[^"\']*["\'][^>]*>(.*?)</table\s*>',s,re.I|re.S)
    if not m: raise ValueError('table not found')
    return matches(r'<tr\b[^>]*>(.*?)</tr\s*>',m[1])
def cells(row): return matches(r'<td\b[^>]*>(.*?)</td\s*>',row)
def date(s): return dt.datetime.strptime(re.search(r'\d{2}\.\d{2}\.\d{4}',s)[0],'%d.%m.%Y').date()
def times(s):
    a,b=re.search(r'(\d{2}:\d{2})\s*[-–]\s*(\d{2}:\d{2})',s).groups()
    if dt.time.fromisoformat(a)>=dt.time.fromisoformat(b): raise ValueError('invalid time')
    return a,b

def parse_week(s, monday, url):
    rows=table(s)
    if len(rows)!=9 or len(cells(rows[0]))!=7: raise ValueError('unexpected weekly grid')
    days=[date(clean(c)) for c in cells(rows[0])[1:]]
    if days!=[monday+dt.timedelta(days=i) for i in range(6)]: raise ValueError('wrong week')
    result=[]
    for i,row in enumerate(rows[1:],1):
        c=cells(row)
        if len(c)!=7 or not re.match(fr'{i}\s+пара\b',clean(c[0])): raise ValueError('wrong lesson slot')
        a,b=times(clean(c[0]))
        for day,cell in zip(days,c[1:]):
            if not clean(cell): continue
            for block in (x for x in re.split(r'(?=<b\b[^>]*>)',cell,flags=re.I|re.S) if clean(x)):
                rooms=matches(r'<b\b[^>]*>(.*?)</b\s*>',block)
                room=clean(rooms[0]) if rooms else ''
                parts=[clean(x) for x in re.split(r'<br\s*/?\s*>',block,flags=re.I) if clean(x)]
                subject=parts[1] if room and parts[0]==room else parts[0]
                m=re.fullmatch(r'(.+?)\s*\((ЛЕКЦ|ЛР|ПЗ|СЕМ|ЗАЧ|ЭКЗ)\)',subject)
                if not m: raise ValueError('unknown subject/type format: '+subject[:100])
                teacher=' / '.join(map(clean,matches(r'<a\b[^>]*href\s*=\s*["\'][^"\']*www_Pgrid\.jsp[^"\']*["\'][^>]*>(.*?)</a\s*>',block)))
                if not teacher or not room: raise ValueError('missing teacher/room')
                period=' / '.join(p for p in parts if re.match(r'^\d{1,2}\s+[а-яё]+\s*[-–]\s*\d{1,2}\s+[а-яё]+',p,re.I))
                subgroup=' / '.join(map(clean,matches(r'<span\b[^>]*>(.*?)</span\s*>',block)))
                result.append(dict(zip(FIELDS,(day.isoformat(),a,b,i,m[1].strip(),m[2],teacher,room,period,subgroup,clean(block),url,'lesson'))))
    return result

def parse_exams(s,url):
    if not re.search(r'<title[^>]*>[^<]*экзамен',s,re.I|re.S): raise ValueError('wrong exam page')
    result=[]
    for row in table(s)[1:]:
        c=list(map(clean,matches(r'<div\b[^>]*class\s*=\s*["\'][^"\']*\bmy_td\b[^"\']*["\'][^>]*>(.*?)</div\s*>',row)))
        if len(c)!=6 or not all(c): raise ValueError('invalid exam row')
        d=date(c[0]); a,b=times(c[1]);
        if not EXAM<=d<=END: raise ValueError('exam outside configured session')
        result.append(dict(zip(FIELDS,(d.isoformat(),a,b,'',c[2],c[3],c[4],c[5],'','',' | '.join(c),url,'exam'))))
    if not result: raise ValueError('empty exam table')
    return result

def fetch(url):
    req=Request(url,headers={'User-Agent':'Mozilla/5.0 (compatible; KNITU-StudyHub/1.2)','Accept':'text/html'})
    with urlopen(req,timeout=25) as r:
        if not r.geturl().startswith(('https://www.kstu.ru/','https://kstu.ru/')): raise ValueError('unexpected redirect')
        raw=r.read(2_000_001)
        if len(raw)>2_000_000: raise ValueError('oversized page')
        return raw.decode(r.headers.get_content_charset() or 'utf-8-sig',errors='strict')

def collect(old,fixture=None,allow_empty=False):
    entries=[]; coverage=[]; failures=[]
    for i in range(10):
        exam=i==9; d=EXAM if exam else START+dt.timedelta(days=7*i)
        name='exams' if exam else 'week_'+str(d)
        url=f'https://www.kstu.ru/www_GEgrid.jsp?d={d}&f=297&g=47638&idk=55952' if exam else f'https://www.kstu.ru/www_Ggrid.jsp?d={d}&g=47638&f=297&idk=55951'
        try:
            raw=(fixture/(name+'.html')).read_text(encoding='utf-8-sig') if fixture else fetch(url)
            items=parse_exams(raw,url) if exam else parse_week(raw,d,url)
            through=END if exam else d+dt.timedelta(days=5)
            if not exam and not items and not allow_empty and any(e['Category']=='lesson' and str(d)<=e['Date']<=str(through) for e in old['entries']): raise ValueError('previously populated week is empty; manual verification required')
            entries+=items
            coverage.append(dict(Kind='exams' if exam else 'week',Date=str(d),Through=str(through),Status='online',Count=len(items),Source=url,Note='Exam table parsed.' if exam else 'Mon-Sat verified; Sunday not provided by page.'))
            print(name,len(items),flush=True)
        except Exception as e:
            failures.append(name); print(f'{name}: {type(e).__name__}: {e}',file=sys.stderr,flush=True)
            if not fixture: break  # avoid repeated requests on an unavailable host
        if not fixture: time.sleep(1)
    if failures: raise ValueError('Failed blocks: '+', '.join(failures))
    entries.sort(key=lambda x:(x['Date'],x['Start'],x['Category'],x['Subject'],x['Teacher'],x['Room']))
    if len({key(e) for e in entries})!=len(entries): raise ValueError('duplicate records')
    return entries,coverage

def key(e): return tuple(str(e.get(k,'')) for k in FIELDS if k not in ('Source','Details'))
def changes(old,new,stamp):
    a={key(e):e for e in old}; b={key(e):e for e in new}; removed=[a[k] for k in sorted(a.keys()-b.keys())]; added=[b[k] for k in sorted(b.keys()-a.keys())]
    result=[]
    for e in removed[:]:
        candidates=[x for x in added if (x['Date'],x['Pair'],x['Start'],x['Subject'],x['Category'])==(e['Date'],e['Pair'],e['Start'],e['Subject'],e['Category'])]
        if len(candidates)==1:
            n=candidates[0]; result.append(dict(at=stamp,kind='changed',before=e,after=n)); removed.remove(e);added.remove(n)
    result.extend(dict(at=stamp,kind='removed',before=e) for e in removed)
    result.extend(dict(at=stamp,kind='added',after=e) for e in added)
    return result

def write_json(path,d): path.write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
def load_content(path, base):
    c=json.loads(path.read_text(encoding='utf-8-sig'))
    def require(ok,msg):
        if not ok: raise ValueError('content.json: '+msg)
    def text(v,limit=4000): return isinstance(v,str) and 0<len(v.strip())<=limit
    def date(v):
        try: return isinstance(v,str) and dt.date.fromisoformat(v).isoformat()==v
        except (ValueError,TypeError): return False
    require(c.get('schema')==1 and c.get('group')==GROUP and date(c.get('updated')), 'schema/group/date')
    tasks=c.get('tasks'); require(isinstance(tasks,list) and 1<=len(tasks)<=1000,'tasks')
    ids=set()
    for t in tasks:
        require(isinstance(t,dict) and isinstance(t.get('id'),str) and re.fullmatch(r'[A-Za-z0-9_-]{1,60}',t['id']) and t['id'] not in ids,'task ID')
        ids.add(t['id']); require(t.get('subject') in base['subjects'],'subject')
        require(all(text(t.get(k)) for k in ('title','description','source','deadlineNote')),'required task fields')
        require(t.get('deadline')=='' or date(t.get('deadline')),'task date')
    require({t['id'] for t in base['tasks']}<=ids,'existing task IDs must be preserved')
    byid={t['id']:t for t in tasks}; dl=c.get('deadlines'); require(isinstance(dl,list) and len(dl)<=1000,'deadlines')
    seen=set()
    for d in dl:
        require(isinstance(d,dict) and date(d.get('date')) and d.get('subject') in base['subjects'].values() and text(d.get('status')) and text(d.get('source')),'deadline fields')
        require(isinstance(d.get('task_ids'),list) and bool(d['task_ids']),'deadline task IDs')
        for id in d['task_ids']:
            require(isinstance(id,str) and id in byid and id not in seen,'deadline task reference')
            seen.add(id); require(byid[id]['deadline']==d['date'] and base['subjects'][byid[id]['subject']]==d['subject'],'deadline mismatch')
    for key,fields in [('announcements',('title','body','source')),('content_changes',('note',))]:
        arr=c.get(key); require(isinstance(arr,list) and len(arr)<=100,'list '+key)
        for a in arr: require(isinstance(a,dict) and date(a.get('date')) and all(text(a.get(k)) for k in fields),'item '+key)
    return {k:c[k] for k in ('updated','tasks','deadlines','announcements','content_changes')}

def run():
    p=argparse.ArgumentParser();p.add_argument('--fixture',type=pathlib.Path);p.add_argument('--out',type=pathlib.Path,default=ROOT/'_site');p.add_argument('--data',type=pathlib.Path,default=ROOT/'data.json');p.add_argument('--allow-empty-week',action='store_true');args=p.parse_args()
    data=json.loads(args.data.read_text(encoding='utf-8-sig')); old=data['schedule']; public_content=load_content(ROOT/'content.json',data); stamp=dt.datetime.now(MSK).isoformat(timespec='seconds')
    if old['group']!=GROUP or old['start']!=str(START) or old['end']!=str(END): raise ValueError('unexpected schedule scope; update configuration manually')
    sync=dict(checked_at=stamp,status='unverified',message='Проверка не выполнена',coverage_end=str(END),changed=0)
    if dt.date.fromisoformat(stamp[:10])>END and not args.fixture:
        sync.update(status='ended',message='Период расписания завершён. Требуется настройка нового семестра.')
    else:
        try:
            entries,coverage=collect(old,args.fixture,args.allow_empty_week)
            journal=changes(old['entries'],entries,stamp)
            if journal:
                data['schedule']={**old,'entries':entries,'coverage':coverage,'created':stamp}
                data['schedule_changes']=(journal+data.get('schedule_changes',[]))[:100]
                if not args.fixture: write_json(args.data,data)
            sync.update(status='fixture' if args.fixture else 'ok',message='Проверены 9 недель и сессия; '+('обнаружены изменения' if journal else 'изменений нет'),changed=len(journal))
        except Exception as e:
            print(f'WARNING: {e}; using stored snapshot',file=sys.stderr)
            sync.update(status='failed',message='Не удалось подтвердить расписание полностью. Сохранена последняя достоверная выгрузка.')
    args.out.mkdir(parents=True,exist_ok=True)
    for name in ASSETS: shutil.copy2(ROOT/name,args.out/name)
    data.update(public_content); data['sync']=sync; data['version']='1.2'; write_json(args.out/'data.json',data)
    print(json.dumps(sync,ensure_ascii=False))
    if args.fixture and sync['status']!='fixture': sys.exit(1)

if __name__=='__main__': run()
