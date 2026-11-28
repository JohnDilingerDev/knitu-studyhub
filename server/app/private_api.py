"""Private endpoints: bearer sessions, scoped roles and atomic audit."""
import hashlib
import os
import secrets
import time
import uuid
from datetime import date, datetime, timezone, timedelta
from typing import Literal
from fastapi import Depends, HTTPException, Response
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, Field, ConfigDict
from sqlalchemy import select, func
from sqlalchemy.exc import IntegrityError
from .models import (User, Membership, Group, Task, Subject, Progress, Snapshot,
                     Announcement, AuthSession, UsedLaunch, AuditEvent)
from .auth import may_edit_group
from .max_auth import verify_launch, InvalidLaunch, SESSION_TTL

class Input(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)

class Launch(Input):
    init_data: str = Field(min_length=1,max_length=16384)

class Mark(Input):
    status: Literal['not_started','in_progress','prepared','checked','submitted','accepted','revise','not_required','clarify']

class Digit(Input):
    digit: int | None = Field(ge=0,le=9,strict=True)

class TaskInput(Input):
    subject: str = Field(min_length=1,max_length=32)
    title: str = Field(min_length=1,max_length=255)
    description: str = Field(min_length=1,max_length=10000)
    deadline: date | None = None
    deadlineNote: str = Field(default='',max_length=1000)
    source: str = Field(min_length=1,max_length=1000)
    show_deadline: bool | None = None

class AnnouncementInput(Input):
    date: date
    title: str = Field(min_length=1,max_length=255)
    body: str = Field(min_length=1,max_length=10000)
    source: str = Field(min_length=1,max_length=1000)

def token_hash(token): return hashlib.sha256(token.encode()).hexdigest()
def msk_today(): return datetime.now(timezone(timedelta(hours=3))).date().isoformat()
def task_view(t):
    return dict(id=t.code,subject=t.subject_code,title=t.title,description=t.description,
                deadline=t.deadline.isoformat() if t.deadline else '',deadlineNote=t.deadline_note,
                source=t.source,active=t.active)

def register(app, db):
    bearer=HTTPBearer(auto_error=False)
    def current(response:Response, credentials:HTTPAuthorizationCredentials|None=Depends(bearer), s=Depends(db)):
        response.headers['Cache-Control']='no-store'
        if not os.environ.get('MAX_BOT_TOKEN','').strip():
            raise HTTPException(503,'MAX authentication is not configured')
        if not credentials or len(credentials.credentials)>128:
            raise HTTPException(401,'Authentication required',headers={'WWW-Authenticate':'Bearer','Cache-Control':'no-store'})
        session=s.get(AuthSession,token_hash(credentials.credentials))
        u=s.get(User,session.user_id) if session and session.expires_at>int(time.time()) else None
        if not u or not u.active:
            raise HTTPException(401,'Invalid session',headers={'WWW-Authenticate':'Bearer','Cache-Control':'no-store'})
        return u,session
    def scoped(s,slug,u,edit=False):
        g=s.scalar(select(Group).where(Group.slug==slug))
        if not g: raise HTTPException(404,'Group not found')
        member=s.get(Membership,(g.id,u.id))
        if edit:
            if not may_edit_group(s,u.id,g.id): raise HTTPException(403,'Forbidden')
        elif not member: raise HTTPException(403,'Membership required')
        return g,member
    def lock_snapshot(s,g):
        snapshot=s.scalar(select(Snapshot).where(Snapshot.group_id==g.id).with_for_update())
        if not snapshot: raise HTTPException(409,'No academic snapshot')
        return snapshot
    def audit(s,u,g,action,code,details,snapshot):
        s.add(AuditEvent(actor_id=u.id,group_id=g.id,action=action,object_code=code,
                         occurred_at=int(time.time()),details=details))
        cm=dict(snapshot.content_meta)
        cm['updated']=msk_today()
        cm['content_changes']=[{'date':msk_today(),'note':f'{action}: {code}'}]+list(cm.get('content_changes',[]))[:99]
        snapshot.content_meta=cm
    @app.post('/api/v1/auth/max')
    def login(response:Response, body:Launch|None=None,s=Depends(db)):
        response.headers['Cache-Control']='no-store'
        bot_token=os.environ.get('MAX_BOT_TOKEN','').strip()
        if not bot_token: raise HTTPException(503,'MAX authentication is not configured')
        if not body: raise HTTPException(400,'init_data required')
        now=int(time.time())
        try: uid,signature,expires=verify_launch(body.init_data,bot_token,now)
        except InvalidLaunch: raise HTTPException(401,'Invalid or expired MAX launch') from None
        u=s.scalar(select(User).where(User.max_user_id==uid))
        if not u or not u.active: raise HTTPException(403,'Access not provisioned')
        token=secrets.token_urlsafe(32)
        try:
            s.add(UsedLaunch(signature=signature,expires_at=expires));s.flush()
            s.add(AuthSession(token_hash=token_hash(token),user_id=u.id,expires_at=now+SESSION_TTL));s.commit()
        except IntegrityError:
            s.rollback();raise HTTPException(401,'Launch already used') from None
        return {'access_token':token,'token_type':'Bearer','expires_in':SESSION_TTL}
    @app.get('/api/v1/me')
    def me(actor=Depends(current),s=Depends(db)):
        u,_=actor
        rows=s.execute(select(Membership,Group).join(Group,Membership.group_id==Group.id).where(Membership.user_id==u.id)).all()
        return {'id':u.id,'owner':u.owner,'groups':[{'slug':g.slug,'role':m.role,'digit':m.digit} for m,g in rows]}
    @app.post('/api/v1/auth/logout')
    def logout(actor=Depends(current),s=Depends(db)):
        s.delete(actor[1]);s.commit();return {'ok':True}
    @app.get('/api/v1/groups/{slug}/me/progress')
    def progress(slug:str,actor=Depends(current),s=Depends(db)):
        u,_=actor;g,m=scoped(s,slug,u)
        rows=s.scalars(select(Progress).where(Progress.group_id==g.id,Progress.user_id==u.id))
        return {'digit':m.digit,'progress':{p.task_code:p.status for p in rows}}
    @app.put('/api/v1/groups/{slug}/me/digit')
    def set_digit(slug:str,body:Digit,actor=Depends(current),s=Depends(db)):
        u,_=actor;g,m=scoped(s,slug,u);m.digit=body.digit;s.commit();return {'digit':m.digit}
    @app.put('/api/v1/groups/{slug}/me/progress/{code}')
    def set_mark(slug:str,code:str,body:Mark,actor=Depends(current),s=Depends(db)):
        u,_=actor;g,_=scoped(s,slug,u);t=s.get(Task,(g.id,code))
        if not t or not t.active: raise HTTPException(404,'Task not found')
        # Serialize writes for this membership, including first insert.
        s.scalar(select(Membership).where(Membership.group_id==g.id,Membership.user_id==u.id).with_for_update())
        s.merge(Progress(group_id=g.id,user_id=u.id,task_code=code,status=body.status));s.commit()
        return {'id':code,'status':body.status}
    def save_task(s,slug,u,body,code=None):
        g,_=scoped(s,slug,u,True);snapshot=lock_snapshot(s,g)
        if not s.get(Subject,(g.id,body.subject)): raise HTTPException(422,'Unknown subject')
        if body.show_deadline is True and not body.deadline: raise HTTPException(422,'Deadline required')
        if code is None:
            code='T'+uuid.uuid4().hex
            order=s.scalar(select(func.max(Task.sort_order)).where(Task.group_id==g.id))
            t=Task(group_id=g.id,code=code,sort_order=(order if order is not None else -1)+1,active=True);s.add(t);before=None
        else:
            t=s.get(Task,(g.id,code))
            if not t or not t.active: raise HTTPException(404,'Task not found')
            before=task_view(t)
        t.subject_code=body.subject;t.title=body.title;t.description=body.description;t.deadline=body.deadline
        t.deadline_note=body.deadlineNote;t.source=body.source
        cm=dict(snapshot.content_meta)
        existing=cm.get('deadlines',[])
        listed=any(code in d['task_ids'] for d in existing)
        show=body.show_deadline if body.show_deadline is not None else listed and bool(body.deadline)
        deadlines=[]
        for d in existing:
            ids=[x for x in d['task_ids'] if x!=code]
            if ids: deadlines.append({**d,'task_ids':ids})
        if show:
            deadlines.append({'date':body.deadline.isoformat(),'subject':s.get(Subject,(g.id,body.subject)).title,
                              'status':body.deadlineNote or 'Срок указан администратором','task_ids':[code],'source':body.source})
        cm['deadlines']=sorted(deadlines,key=lambda d:d['date']);snapshot.content_meta=cm
        after=task_view(t);audit(s,u,g,'task.create' if before is None else 'task.update',code,{'before':before,'after':after},snapshot)
        s.commit();return after
    @app.post('/api/v1/groups/{slug}/admin/tasks',status_code=201)
    def create_task(slug:str,body:TaskInput,actor=Depends(current),s=Depends(db)):
        return save_task(s,slug,actor[0],body)
    @app.put('/api/v1/groups/{slug}/admin/tasks/{code}')
    def update_task(slug:str,code:str,body:TaskInput,actor=Depends(current),s=Depends(db)):
        return save_task(s,slug,actor[0],body,code)
    @app.get('/api/v1/groups/{slug}/admin/announcements')
    def list_announcements(slug:str,actor=Depends(current),s=Depends(db)):
        g,_=scoped(s,slug,actor[0],True)
        return [{'id':a.code,**a.payload} for a in s.scalars(select(Announcement).where(Announcement.group_id==g.id).order_by(Announcement.sort_order))]
    def save_announcement(s,slug,u,body,code=None):
        g,_=scoped(s,slug,u,True);snapshot=lock_snapshot(s,g)
        payload=body.model_dump(mode='json')
        if code is None:
            code=uuid.uuid4().hex;order=s.scalar(select(func.max(Announcement.sort_order)).where(Announcement.group_id==g.id))
            a=Announcement(group_id=g.id,code=code,payload=payload,sort_order=(order if order is not None else -1)+1);s.add(a);before=None
        else:
            a=s.get(Announcement,(g.id,code))
            if not a: raise HTTPException(404,'Announcement not found')
            before=a.payload;a.payload=payload
        audit(s,u,g,'announcement.create' if before is None else 'announcement.update',code,{'before':before,'after':payload},snapshot)
        s.commit();return {'id':code,**payload}
    @app.post('/api/v1/groups/{slug}/admin/announcements',status_code=201)
    def create_announcement(slug:str,body:AnnouncementInput,actor=Depends(current),s=Depends(db)):
        return save_announcement(s,slug,actor[0],body)
    @app.put('/api/v1/groups/{slug}/admin/announcements/{code}')
    def update_announcement(slug:str,code:str,body:AnnouncementInput,actor=Depends(current),s=Depends(db)):
        return save_announcement(s,slug,actor[0],body,code)
    @app.get('/api/v1/groups/{slug}/admin/audit')
    def audit_list(slug:str,actor=Depends(current),s=Depends(db)):
        g,_=scoped(s,slug,actor[0],True)
        rows=s.scalars(select(AuditEvent).where(AuditEvent.group_id==g.id).order_by(AuditEvent.id.desc()).limit(100))
        return [dict(id=a.id,actor_id=a.actor_id,action=a.action,object_code=a.object_code,occurred_at=a.occurred_at,details=a.details) for a in rows]
