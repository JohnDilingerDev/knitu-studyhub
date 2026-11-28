import os,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]

def test_backup_atomic_and_checksum(tmp_path):
    fake=tmp_path/'bin';fake.mkdir();docker=fake/'docker';docker.write_text('#!/bin/sh\nif [ "${FAIL_DUMP:-}" = 1 ]; then echo partial; exit 4; fi\nprintf "CREATE TABLE test (id INT);\\n"\n');docker.chmod(0o700)
    env={**os.environ,'PATH':str(fake)+':'+os.environ['PATH']}
    dest=tmp_path/'backups'
    cmd=['bash',str(ROOT/'ops/backup.sh'),str(dest)]
    out=subprocess.run(cmd,env=env,check=True,capture_output=True,text=True)
    backup=Path(out.stdout.strip());assert backup.is_dir();assert dest.stat().st_mode&0o777==0o700
    assert (backup/'database.sql.gz').stat().st_mode&0o777==0o600
    verify=['bash',str(ROOT/'ops/verify-backup.sh'),str(backup)]
    subprocess.run(verify,check=True,capture_output=True)
    result=subprocess.run(cmd,env={**env,'FAIL_DUMP':'1'},capture_output=True);assert result.returncode!=0
    assert list(dest.iterdir())==[backup]
    with (backup/'database.sql.gz').open('ab') as f:f.write(b'corruption')
    assert subprocess.run(verify,capture_output=True).returncode!=0
