from fastapi import FastAPI, Depends, HTTPException, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pathlib import Path
from sqlalchemy import select, text
from datetime import date
from typing import Optional
from contextlib import asynccontextmanager
from .db import make_engine,database_url,session_factory
from .private_api import register
from .models import Group,Subject,Task,ScheduleEntry,Variant,Snapshot,Announcement

def create_app(engine=None):
    @asynccontextmanager
    async def lifespan(app):
        app.state.engine=engine if engine is not None else make_engine(database_url())
        app.state.sessions=session_factory(app.state.engine)
        yield
        if engine is None: app.state.engine.dispose()
    app=FastAPI(title='StudyHub API',version='1.3.2-dev',lifespan=lifespan)
    def db():
        with app.state.sessions() as s: yield s
    def group(slug,s):
        g=s.scalar(select(Group).where(Group.slug==slug,Group.public.is_(True)))
        if not g: raise HTTPException(404,'Group not found')
        return g
    def tasks(s,g):
        return [dict(id=t.code,subject=t.subject_code,title=t.title,description=t.description,deadline=t.deadline.isoformat() if t.deadline else '',deadlineNote=t.deadline_note,source=t.source) for t in s.scalars(select(Task).where(Task.group_id==g,Task.active.is_(True)).order_by(Task.sort_order))]
    def entries(s,g,start=None,end=None):
        q=select(ScheduleEntry).where(ScheduleEntry.group_id==g)
        if start: q=q.where(ScheduleEntry.day>=start)
        if end: q=q.where(ScheduleEntry.day<=end)
        return [e.payload for e in s.scalars(q.order_by(ScheduleEntry.sort_order))]
    def variant_rows(s,g):
        return list(s.scalars(select(Variant).where(Variant.group_id==g).order_by(Variant.task_number,Variant.variant_number)))
    @app.get('/health')
    def health(s=Depends(db)):
        s.execute(text('SELECT 1'));return {'status':'ok','version':'1.3.2-dev'}
    @app.get('/api/v1/groups')
    def groups(s=Depends(db)):
        return [{'slug':g.slug,'code':g.code,'term':g.term} for g in s.scalars(select(Group).where(Group.public.is_(True)).order_by(Group.slug))]
    @app.get('/api/v1/groups/{slug}/tasks')
    def get_tasks(slug:str,s=Depends(db)): return tasks(s,group(slug,s).id)
    @app.get('/api/v1/groups/{slug}/schedule')
    def get_schedule(slug:str,start:Optional[date]=None,end:Optional[date]=None,s=Depends(db)):
        if start and end and start>end: raise HTTPException(422,'start must not exceed end')
        g=group(slug,s).id; meta=s.get(Snapshot,g)
        return {**(meta.schedule_meta if meta else {}),'entries':entries(s,g,start,end)}
    @app.get('/api/v1/groups/{slug}/variants/{digit}')
    def variants(slug:str,digit:int,s=Depends(db)):
        if not 0<=digit<=9: raise HTTPException(422,'Expected last digit 0..9')
        g=group(slug,s).id; n=digit or 10
        return {'variant':n,'tasks':[{'number':v.task_number,'topic':v.topic} for v in variant_rows(s,g) if v.variant_number==n]}
    @app.get('/api/v1/groups/{slug}/bundle')
    def bundle(slug:str,s=Depends(db)):
        g=group(slug,s).id; snapshot=s.get(Snapshot,g)
        if not snapshot: raise HTTPException(404,'Data not imported')
        vs=variant_rows(s,g)
        cm=snapshot.content_meta
        return {'version':'1.3.2-dev','updated':cm['updated'],'schedule':{**snapshot.schedule_meta,'entries':entries(s,g)},'subjects':{r.code:r.title for r in s.scalars(select(Subject).where(Subject.group_id==g))},'tasks':tasks(s,g),'variants':[[v.topic for v in vs if v.task_number==i] for i in range(1,5)],'deadlines':cm['deadlines'],'announcements':[a.payload for a in s.scalars(select(Announcement).where(Announcement.group_id==g).order_by(Announcement.sort_order))],'content_changes':cm.get('content_changes',[]),'schedule_changes':cm.get('schedule_changes',[]),**({'sync':cm['sync']} if 'sync' in cm else {})}
    @app.exception_handler(RequestValidationError)
    async def safe_validation(request:Request, exc:RequestValidationError):
        # Do not reflect signed launch data, credentials or personal inputs in errors.
        return JSONResponse(status_code=422,content={'detail':'Invalid request'},headers={'Cache-Control':'no-store'})
    @app.middleware('http')
    async def no_cache(request:Request,call_next):
        response=await call_next(request)
        response.headers['Cache-Control']='no-store'
        response.headers['X-Content-Type-Options']='nosniff'
        response.headers['Referrer-Policy']='no-referrer'
        if request.url.path.startswith('/cabinet'):
            response.headers['Content-Security-Policy']="default-src 'self'; script-src 'self' https://st.max.ru; style-src 'self'; img-src 'self' data:; connect-src 'self'; object-src 'none'; base-uri 'none'; form-action 'self'"
        return response
    register(app,db)
    @app.get('/', include_in_schema=False)
    def cabinet_redirect(): return RedirectResponse('/cabinet/')
    app.mount('/cabinet', StaticFiles(directory=Path(__file__).resolve().parents[1]/'web',html=True), name='cabinet')
    return app

app=create_app()
