import os
from sqlalchemy import create_engine, event, URL
from sqlalchemy.orm import sessionmaker

def database_url():
    if os.environ.get('DATABASE_URL'):
        return os.environ['DATABASE_URL']
    return URL.create('mysql+pymysql',username=os.environ['MYSQL_USER'],password=os.environ['MYSQL_PASSWORD'],host=os.environ.get('MYSQL_HOST','db'),port=int(os.environ.get('MYSQL_PORT','3306')),database=os.environ['MYSQL_DATABASE'],query={'charset':'utf8mb4'})

def make_engine(url):
    engine=create_engine(url,pool_pre_ping=True)
    if engine.dialect.name=='sqlite':
        @event.listens_for(engine,'connect')
        def fk_on(dbapi_connection, _):
            dbapi_connection.execute('PRAGMA foreign_keys=ON')
    return engine

def session_factory(engine):
    return sessionmaker(bind=engine,expire_on_commit=False)
