"""Validate raw MAX Bridge initData; never trust initDataUnsafe or client roles."""
import hashlib
import hmac
import json
import re
import time
from urllib.parse import parse_qsl

MAX_AGE = 300
FUTURE_SKEW = 30
SESSION_TTL = 8 * 3600

class InvalidLaunch(ValueError):
    pass

def verify_launch(raw: str, bot_token: str, now: int | None = None):
    now = int(time.time()) if now is None else now
    try:
        if not raw or len(raw) > 16384 or re.search(r'%(?![0-9a-fA-F]{2})',raw):
            raise ValueError()
        pairs = parse_qsl(raw, keep_blank_values=True, strict_parsing=True,
                          encoding='utf-8', errors='strict', max_num_fields=64)
        fields = dict(pairs)
        if len(fields) != len(pairs):
            raise ValueError()
        signature = fields.pop('hash')
        if not re.fullmatch('[0-9a-f]{64}',signature):
            raise ValueError()
        if any(not re.fullmatch(r'[A-Za-z0-9_]+',k) or '\n' in v or '\r' in v for k,v in fields.items()):
            raise ValueError()
        message = '\n'.join(f'{k}={v}' for k,v in sorted(fields.items()))
        key = hmac.digest(b'WebAppData',bot_token.encode(),'sha256')
        expected = hmac.new(key,message.encode(),hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected,signature):
            raise ValueError()
        stamp = fields['auth_date']
        if not re.fullmatch(r'[0-9]{1,12}',stamp):
            raise ValueError()
        timestamp = int(stamp)
        if not now-MAX_AGE <= timestamp <= now+FUTURE_SKEW:
            raise ValueError()
        user = json.loads(fields['user'])
        uid = user['id']
        if type(uid) is not int or not 0 < uid < 2**63:
            raise ValueError()
        return uid,signature,timestamp+MAX_AGE
    except (ValueError,TypeError,KeyError,UnicodeError,OverflowError,RecursionError) as exc:
        raise InvalidLaunch('Invalid or expired MAX launch') from None
