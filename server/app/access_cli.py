"""Trusted server operator only. No HTTP route can assign roles."""
import argparse
import time
from sqlalchemy import select, delete
from .models import User, Group, Membership, AuthSession, UsedLaunch
from .db import make_engine, database_url, session_factory

def main():
    p=argparse.ArgumentParser(description=__doc__)
    sub=p.add_subparsers(dest='command',required=True)
    grant=sub.add_parser('grant');grant.add_argument('max_id',type=int);grant.add_argument('role',choices=['student','admin','owner']);grant.add_argument('--group')
    revoke=sub.add_parser('disable');revoke.add_argument('max_id',type=int)
    sub.add_parser('cleanup')
    args=p.parse_args();engine=make_engine(database_url());sf=session_factory(engine)
    try:
        with sf.begin() as s:
            if args.command=='cleanup':
                now=int(time.time());s.execute(delete(AuthSession).where(AuthSession.expires_at<=now));s.execute(delete(UsedLaunch).where(UsedLaunch.expires_at<now));return
            if not 0<args.max_id<2**63: p.error('invalid MAX ID')
            u=s.scalar(select(User).where(User.max_user_id==args.max_id))
            if args.command=='disable':
                if not u: p.error('unknown user')
                u.active=False;s.execute(delete(AuthSession).where(AuthSession.user_id==u.id));return
            if args.role!='owner' and not args.group: p.error('--group required')
            g=s.scalar(select(Group).where(Group.slug==args.group)) if args.group else None
            if args.group and not g: p.error('unknown group')
            if not u: u=User(max_user_id=args.max_id);s.add(u);s.flush()
            u.active=True
            if args.role=='owner': u.owner=True
            if g:
                m=s.get(Membership,(g.id,u.id))
                if not m: s.add(Membership(group_id=g.id,user_id=u.id,role='admin' if args.role=='owner' else args.role))
                else: m.role='admin' if args.role=='owner' else args.role
            s.execute(delete(AuthSession).where(AuthSession.user_id==u.id))
        print('Access updated')
    finally: engine.dispose()
if __name__=='__main__': main()
