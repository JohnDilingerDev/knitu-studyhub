"""Import only an explicitly verified, trusted StudyHub published schedule.
This is an operator command, not an internet-facing upload endpoint.
"""
import argparse
import datetime as dt
import json
from sqlalchemy import select, delete
from .db import database_url,make_engine,session_factory
from .models import Group,Snapshot,ScheduleEntry
from .import_data import GROUP,SLUG,digest,load_json

def sync_schedule(s,data,now=None):
    now=now or dt.datetime.now(dt.timezone.utc)
    stamp=dt.datetime.fromisoformat(data['sync']['checked_at'])
    age=(now-stamp).total_seconds()
    if data['sync']['status']!='ok' or not -60<=age<=43200:
        raise ValueError('Schedule is not freshly verified')
    schedule=data['schedule'];entries=schedule['entries'];coverage=schedule['coverage']
    g=s.scalar(select(Group).where(Group.slug==SLUG))
    if not g or schedule['group']!=GROUP or not entries or not coverage: raise ValueError('Wrong or empty schedule')
    snapshot=s.scalar(select(Snapshot).where(Snapshot.group_id==g.id).with_for_update())
    if not snapshot: raise ValueError('Import initial bundle first')
    old=snapshot.schedule_meta
    if any(schedule[k]!=old[k] for k in ('group','start','end')) or data['sync']['coverage_end']!=schedule['end']:
        raise ValueError('Unexpected semester scope')
    previous_sync=snapshot.content_meta.get('sync',{}).get('checked_at')
    if previous_sync and stamp<dt.datetime.fromisoformat(previous_sync): raise ValueError('Older verification')
    if any(x['Status']!='online' for x in coverage): raise ValueError('Unverified coverage')
    if coverage!=old['coverage']:
        # Scope is fixed for this pilot; verify changes in coverage manually.
        # Counts and check times can change, so compare identifiers only.
        def key(x): return (x['Kind'],x['Date'],x['Through'],x['Source'])
        if len(coverage)!=len(old['coverage']) or [key(x) for x in coverage]!=[key(x) for x in old['coverage']]: raise ValueError('Unexpected coverage')
    codes=[digest(e) for e in entries]
    if len(set(codes))!=len(codes): raise ValueError('Duplicate events')
    for e in entries:
        d=dt.date.fromisoformat(e['Date']);a=dt.time.fromisoformat(e['Start']);b=dt.time.fromisoformat(e['End'])
        if not schedule['start']<=d.isoformat()<=schedule['end'] or a>=b: raise ValueError('Invalid event')
    s.execute(delete(ScheduleEntry).where(ScheduleEntry.group_id==g.id))
    for i,(e,code) in enumerate(zip(entries,codes)):
        s.add(ScheduleEntry(group_id=g.id,code=code,day=dt.date.fromisoformat(e['Date']),start=e['Start'],payload=e,sort_order=i))
    snapshot.schedule_meta={k:v for k,v in schedule.items() if k!='entries'}
    snapshot.content_meta={**snapshot.content_meta,'schedule_changes':data.get('schedule_changes',[]),'sync':data['sync']}
    s.flush();return len(entries)

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('verified_json');args=p.parse_args()
    engine=make_engine(database_url());sf=session_factory(engine)
    try:
        with sf.begin() as s: count=sync_schedule(s,load_json(args.verified_json))
        print(json.dumps({'entries':count,'status':'ok'}))
    finally: engine.dispose()
if __name__=='__main__': main()
