"""Authorization skeleton, deliberately no authentication bypass or demo login."""
from sqlalchemy.orm import Session
from .models import User, Membership

def may_edit_group(s:Session, user_id:int, group_id:int)->bool:
    # user_id must come from a server-verified session, never from client input.
    user=s.get(User,user_id)
    if not user or not user.active: return False
    if user.owner: return True
    member=s.get(Membership,(group_id,user_id))
    return bool(member and member.role=='admin')

def may_access_progress(s:Session, actor_id:int, owner_id:int, group_id:int)->bool:
    user=s.get(User,actor_id)
    return bool(user and user.active and actor_id==owner_id and s.get(Membership,(group_id,actor_id)))
