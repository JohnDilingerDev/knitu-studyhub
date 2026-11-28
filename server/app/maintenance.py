"""Operator-only pull of the public, verified StudyHub timetable and session cleanup."""
import argparse
import datetime as dt
import json
import time
from urllib.request import Request, build_opener, HTTPRedirectHandler
from sqlalchemy import delete
from .db import database_url, make_engine, session_factory
from .models import AuthSession, UsedLaunch
from .sync_schedule import sync_schedule

SOURCE = 'https://johndilingerdev.github.io/knitu-studyhub/data.json'
MAX_BYTES = 2 * 1024 * 1024

class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ValueError('Unexpected redirect from timetable source')

def fetch_schedule(opener=None):
    opener = opener or build_opener(NoRedirect())
    request = Request(SOURCE, headers={'Accept': 'application/json', 'Cache-Control': 'no-cache', 'User-Agent': 'StudyHub-maintenance/1.3.3'})
    with opener.open(request, timeout=30) as response:
        if response.geturl() != SOURCE or response.status != 200:
            raise ValueError('Unexpected timetable response')
        raw = response.read(MAX_BYTES + 1)
    if len(raw) > MAX_BYTES:
        raise ValueError('Timetable exceeds size limit')
    data = json.loads(raw.decode('utf-8-sig'))
    if not isinstance(data, dict):
        raise ValueError('Invalid timetable JSON')
    return data

def cleanup(s, now=None):
    now = int(time.time()) if now is None else now
    return {'sessions': s.execute(delete(AuthSession).where(AuthSession.expires_at <= now)).rowcount,
            'launches': s.execute(delete(UsedLaunch).where(UsedLaunch.expires_at < now)).rowcount}

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('command', choices=['sync', 'cleanup', 'all'])
    args = p.parse_args()
    engine = make_engine(database_url())
    sf = session_factory(engine)
    try:
        if args.command in ('cleanup', 'all'):
            with sf.begin() as s:
                result = cleanup(s)
            print(json.dumps({'cleanup': result}))
        if args.command in ('sync', 'all'):
            try:
                data = fetch_schedule()
                with sf.begin() as s:
                    count = sync_schedule(s, data)
            except Exception as exc:
                # Preserve the last verified snapshot. Avoid logging response contents.
                print(json.dumps({'sync': 'failed', 'error_type': type(exc).__name__}))
                raise SystemExit(1) from None
            print(json.dumps({'sync': 'ok', 'entries': count}))
    finally:
        engine.dispose()

if __name__ == '__main__':
    main()
