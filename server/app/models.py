"""StudyHub persistence: every academic record is scoped to a group/term."""
from datetime import date
from sqlalchemy import (String, Integer, BigInteger, Text, Date, Boolean, JSON,
    ForeignKey, ForeignKeyConstraint, UniqueConstraint, CheckConstraint, Index)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

class Base(DeclarativeBase):
    pass

# SQLite is only for local tests. Production uses MySQL/InnoDB and utf8mb4.
class University(Base):
    __tablename__ = 'universities'
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(32), unique=True)
    name: Mapped[str] = mapped_column(String(255))

class Group(Base):
    __tablename__ = 'study_groups'
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    university_id: Mapped[int] = mapped_column(ForeignKey('universities.id'))
    slug: Mapped[str] = mapped_column(String(100), unique=True)
    code: Mapped[str] = mapped_column(String(64))
    term: Mapped[str] = mapped_column(String(32))
    public: Mapped[bool] = mapped_column(Boolean, default=False)
    __table_args__ = (UniqueConstraint('university_id','code','term',name='uq_group_term'),)

class User(Base):
    __tablename__ = 'users'
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    # Store only the stable identifier, not names, phones or bot tokens.
    max_user_id: Mapped[int] = mapped_column(BigInteger, unique=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    owner: Mapped[bool] = mapped_column(Boolean, default=False)

class Membership(Base):
    __tablename__ = 'memberships'
    group_id: Mapped[int] = mapped_column(ForeignKey('study_groups.id'), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id'), primary_key=True)
    role: Mapped[str] = mapped_column(String(16))
    digit: Mapped[int|None] = mapped_column(Integer, nullable=True)
    __table_args__ = (CheckConstraint("role IN ('student','admin')",name='ck_member_role'), CheckConstraint('digit IS NULL OR digit BETWEEN 0 AND 9',name='ck_member_digit'))

class Subject(Base):
    __tablename__ = 'subjects'
    group_id: Mapped[int] = mapped_column(ForeignKey('study_groups.id'), primary_key=True)
    code: Mapped[str] = mapped_column(String(32), primary_key=True)
    title: Mapped[str] = mapped_column(String(255))

class Task(Base):
    __tablename__ = 'tasks'
    group_id: Mapped[int] = mapped_column(ForeignKey('study_groups.id'), primary_key=True)
    code: Mapped[str] = mapped_column(String(64), primary_key=True)
    subject_code: Mapped[str] = mapped_column(String(32))
    title: Mapped[str] = mapped_column(String(255))
    description: Mapped[str] = mapped_column(Text)
    deadline: Mapped[date|None] = mapped_column(Date, nullable=True)
    deadline_note: Mapped[str] = mapped_column(Text)
    source: Mapped[str] = mapped_column(Text)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    sort_order: Mapped[int] = mapped_column(Integer)
    __table_args__ = (ForeignKeyConstraint(['group_id','subject_code'],['subjects.group_id','subjects.code'],name='fk_task_subject'),)

class Progress(Base):
    __tablename__ = 'progress'
    group_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    task_code: Mapped[str] = mapped_column(String(64), primary_key=True)
    status: Mapped[str] = mapped_column(String(32))
    __table_args__ = (ForeignKeyConstraint(['group_id','user_id'],['memberships.group_id','memberships.user_id'],name='fk_progress_member'),ForeignKeyConstraint(['group_id','task_code'],['tasks.group_id','tasks.code'],name='fk_progress_task'),CheckConstraint("status IN ('not_started','in_progress','prepared','checked','submitted','accepted','revise','not_required','clarify')",name='ck_progress_status'))

class ScheduleEntry(Base):
    __tablename__ = 'schedule_entries'
    group_id: Mapped[int] = mapped_column(ForeignKey('study_groups.id'), primary_key=True)
    code: Mapped[str] = mapped_column(String(64), primary_key=True)
    day: Mapped[date] = mapped_column(Date)
    start: Mapped[str] = mapped_column(String(5))
    payload: Mapped[dict] = mapped_column(JSON)
    sort_order: Mapped[int] = mapped_column(Integer)
    __table_args__ = (Index('ix_schedule_group_day','group_id','day','start'),)

class Variant(Base):
    __tablename__ = 'variants'
    group_id: Mapped[int] = mapped_column(ForeignKey('study_groups.id'), primary_key=True)
    task_number: Mapped[int] = mapped_column(Integer, primary_key=True)
    variant_number: Mapped[int] = mapped_column(Integer, primary_key=True)
    topic: Mapped[str] = mapped_column(Text)
    __table_args__ = (CheckConstraint('variant_number BETWEEN 1 AND 10',name='ck_variant_number'), CheckConstraint('task_number BETWEEN 1 AND 4',name='ck_variant_task'))

class Snapshot(Base):
    __tablename__ = 'group_snapshots'
    group_id: Mapped[int] = mapped_column(ForeignKey('study_groups.id'), primary_key=True)
    # Retain exact original metadata including coverage and source provenance.
    schedule_meta: Mapped[dict] = mapped_column(JSON)
    content_meta: Mapped[dict] = mapped_column(JSON)

class Announcement(Base):
    __tablename__ = 'announcements'
    group_id: Mapped[int] = mapped_column(ForeignKey('study_groups.id'), primary_key=True)
    code: Mapped[str] = mapped_column(String(64), primary_key=True)
    payload: Mapped[dict] = mapped_column(JSON)
    sort_order: Mapped[int] = mapped_column(Integer)

# Apply explicit storage parameters for all MySQL tables.
for table in Base.metadata.tables.values():
    table.dialect_options['mysql']['engine'] = 'InnoDB'
    table.dialect_options['mysql']['charset'] = 'utf8mb4'
    table.dialect_options['mysql']['collate'] = 'utf8mb4_0900_as_cs'
