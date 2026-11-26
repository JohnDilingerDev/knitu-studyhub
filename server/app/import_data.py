"""Trusted operator-only import. Never import arbitrary user-provided JSON."""
import argparse, datetime as dt, hashlib, json
from pathlib import Path
from sqlalchemy import select, delete
from .models import University, Group, Subject, Task, ScheduleEntry, Variant, Snapshot, Announcement
from .db import database_url, make_engine, session_factory

SLUG='knitu-661-m52-2026-1'
GROUP='661-М52 ИППБТ'
def digest(x):
    return hashlib.sha256(json.dumps(x,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()
def load_json(path): return json.loads(Path(path).read_text(encoding='utf-8-sig'))

def validate(data, content):
    if data['schedule']['group']!=GROUP or content['group']!=GROUP:
        raise ValueError('wrong group')
    tasks=content['tasks']; entries=data['schedule']['entries']; variants=data['variants']; anns=content['announcements']
    ids=[t['id'] for t in tasks]
    if len(set(ids))!=len(ids) or not tasks or not entries or not data['schedule']['coverage']:
        raise ValueError('empty or duplicate data')
    if len(variants)!=4 or any(len(v)!=10 for v in variants): raise ValueError('wrong variant matrix')
    if any(t['subject'] not in data['subjects'] or not t['title'] for t in tasks): raise ValueError('unknown subject or empty task')
    for t in tasks:
        if t.get('deadline'): dt.date.fromisoformat(t['deadline'])
    for d in content['deadlines']:
        dt.date.fromisoformat(d['date'])
        if not set(d['task_ids']) <= set(ids): raise ValueError('unknown deadline task')
    for e in entries:
        day=dt.date.fromisoformat(e['Date']); start=dt.time.fromisoformat(e['Start']); end=dt.time.fromisoformat(e['End'])
        if not data['schedule']['start']<=e['Date']<=data['schedule']['end'] or start>=end: raise ValueError('invalid entry')
    if len({digest(e) for e in entries})!=len(entries): raise ValueError('duplicate entries')
    if len({digest(a) for a in anns})!=len(anns): raise ValueError('duplicate announcements')
    return tasks,entries,variants,anns

def import_bundle(s,data,content):
    tasks,entries,variants,anns=validate(data,content)
    uni=s.scalar(select(University).where(University.code=='knitu'))
    if not uni:
        uni=University(code='knitu',name='Казанский национальный исследовательский технологический университет');s.add(uni);s.flush()
    group=s.scalar(select(Group).where(Group.slug==SLUG))
    if not group:
        group=Group(university_id=uni.id,slug=SLUG,code=GROUP,term='2026/2027-1',public=True);s.add(group);s.flush()
    g=group.id
    for code,title in data['subjects'].items(): s.merge(Subject(group_id=g,code=code,title=title))
    s.flush()
    incoming={t['id'] for t in tasks}
    for t in s.scalars(select(Task).where(Task.group_id==g)):
        if t.code not in incoming: t.active=False # preserve student progress
    for i,t in enumerate(tasks):
        s.merge(Task(group_id=g,code=t['id'],subject_code=t['subject'],title=t['title'],description=t['description'],deadline=dt.date.fromisoformat(t['deadline']) if t.get('deadline') else None,deadline_note=t.get('deadlineNote',''),source=t.get('source',''),active=True,sort_order=i))
    for model in (ScheduleEntry,Variant,Announcement): s.execute(delete(model).where(model.group_id==g))
    for i,e in enumerate(entries): s.add(ScheduleEntry(group_id=g,code=digest(e),day=dt.date.fromisoformat(e['Date']),start=e['Start'],payload=e,sort_order=i))
    for i,row in enumerate(variants,1):
        for j,topic in enumerate(row,1): s.add(Variant(group_id=g,task_number=i,variant_number=j,topic=topic))
    for i,a in enumerate(anns): s.add(Announcement(group_id=g,code=digest(a),payload=a,sort_order=i))
    schedule_meta={k:v for k,v in data['schedule'].items() if k!='entries'}
    content_meta={k:v for k,v in content.items() if k not in ('tasks','announcements')}
    content_meta['schedule_updated']=data['updated'];content_meta['schedule_changes']=data.get('schedule_changes',[])
    s.merge(Snapshot(group_id=g,schedule_meta=schedule_meta,content_meta=content_meta))
    s.flush()
    return {'tasks':len(tasks),'entries':len(entries),'variants':sum(map(len,variants)),'announcements':len(anns)}

def main():
    p=argparse.ArgumentParser();p.add_argument('--data',default='seed/data.json');p.add_argument('--content',default='seed/content.json');args=p.parse_args()
    sf=session_factory(make_engine(database_url()))
    with sf.begin() as s: result=import_bundle(s,load_json(args.data),load_json(args.content))
    print(json.dumps(result,ensure_ascii=False))
if __name__=='__main__': main()
