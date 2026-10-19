"""Opt-in installed-CLI contract test. Deletes ONLY its own TemporaryDirectory.
Run: python tests/probe_official_delete.py
No real CODEX_HOME is ever passed to a mutating command.
"""
import json
import msvcrt
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import uuid
import sys
import sqlite3
from contextlib import closing

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from cleaner.activity import probe_file
from cleaner.core import detect_cli, run_cli


def main():
    cli = shutil.which('codex')
    assert cli, 'CLI missing'
    with tempfile.TemporaryDirectory(prefix='cleaner-online-contract-') as td:
        home = Path(td).resolve()
        detected = detect_cli(home, cli)
        assert detected['available'] and detected['lock_verified'], detected
        env = os.environ.copy()
        env['CODEX_HOME'] = str(home)
        for name in ('CODEX_THREAD_ID', 'CODEX_SESSION_ID'):
            env.pop(name, None)
        sid = str(uuid.uuid4())
        path = home / 'sessions' / f'rollout-2026-09-16T00-00-00-{sid}.jsonl'
        path.parent.mkdir()
        path.write_text(json.dumps({'timestamp':'2026-09-16T00:00:00Z','type':'session_meta','payload':{
            'id':sid,'timestamp':'2026-09-16T00:00:00Z','cwd':str(home),'originator':'codex_cli_rs',
            'cli_version':detected['version'].removeprefix('codex-cli '),'source':'cli','model_provider':'openai'}})+'\n', encoding='utf-8')
        locks = home / 'thread-writer-locks'
        locks.mkdir()
        lock = locks / f'{sid}.lock'
        lock.write_bytes(b'')
        with lock.open('r+b') as held:
            msvcrt.locking(held.fileno(), msvcrt.LK_NBLCK, 1)
            assert probe_file(lock) == 'busy'
            blocked = subprocess.run([cli,'delete','--force',sid],env=env,capture_output=True,encoding='utf-8',errors='replace',timeout=45)
            assert blocked.returncode != 0 and path.exists(), (blocked.stdout, blocked.stderr)
            held.seek(0); msvcrt.locking(held.fileno(), msvcrt.LK_UNLCK, 1)
        assert probe_file(lock) == 'free'
        deleted = subprocess.run([cli,'delete','--force',sid],env=env,capture_output=True,encoding='utf-8',errors='replace',timeout=45)
        assert deleted.returncode == 0 and not path.exists(), (deleted.stdout,deleted.stderr)
        # Seed an orphan in the isolated CLI-created schema; no real DB is copied.
        orphan = str(uuid.uuid4())
        missing = home / 'sessions' / f'rollout-2026-09-16T00-00-00-{orphan}.jsonl'
        db = home / 'state_5.sqlite'
        assert db.exists()
        conn = sqlite3.connect(db)
        try:
            conn.execute('''INSERT INTO threads(id,rollout_path,created_at,updated_at,source,
                model_provider,cwd,title,sandbox_policy,approval_mode)
                VALUES(?,?,0,0,'cli','openai',?,'orphan fixture','read-only','never')''',
                (orphan,str(missing),str(home)))
            conn.execute('INSERT INTO thread_spawn_edges(parent_thread_id,child_thread_id,status) VALUES(?,?,?)', (orphan,str(uuid.uuid4()),'completed'))
            conn.commit()
        finally: conn.close()
        cleaned = subprocess.run([cli,'delete','--force',orphan],env=env,capture_output=True,encoding='utf-8',errors='replace',timeout=45)
        conn = sqlite3.connect(db)
        try: remaining = conn.execute('SELECT count(*) FROM threads WHERE id=?',(orphan,)).fetchone()[0]
        finally: conn.close()
        assert cleaned.returncode == 0 and remaining == 0 and not missing.exists(), (cleaned.stdout,cleaned.stderr,remaining)
        compressed_cases = []
        for direct_reference in (False, True):
            compressed_id = str(uuid.uuid4())
            original = home / 'sessions' / f'rollout-2026-09-16T00-00-00-{compressed_id}.jsonl'
            packed = Path(str(original) + '.zst')
            data = (json.dumps({'timestamp':'2026-09-16T00:00:00Z','type':'session_meta','payload':{
                'id':compressed_id,'timestamp':'2026-09-16T00:00:00Z','cwd':str(home),
                'originator':'codex_cli_rs','cli_version':detected['version'].removeprefix('codex-cli '),
                'source':'cli','model_provider':'openai'}}) + '\n').encode()
            packed.write_bytes(b'\x28\xb5\x2f\xfd\xa0' + len(data).to_bytes(4,'little') +
                               ((len(data) << 3) | 1).to_bytes(3,'little') + data)
            with closing(sqlite3.connect(db)) as conn:
                with conn:
                    conn.execute('''INSERT INTO threads(id,rollout_path,created_at,updated_at,source,
                        model_provider,cwd,title,sandbox_policy,approval_mode)
                        VALUES(?,?,0,0,'cli','openai',?,'compressed fixture','read-only','never')''',
                        (compressed_id, str(packed if direct_reference else original), str(home)))
            outcome = run_cli([cli,'delete','--force',compressed_id], home, timeout=45, isolated=True)
            with closing(sqlite3.connect(db)) as conn:
                remains = conn.execute('SELECT count(*) FROM threads WHERE id=?',(compressed_id,)).fetchone()[0]
            compressed_cases.append({'direct_reference': direct_reference, 'exit_code': outcome.returncode,
                                     'metadata_remaining': remains, 'compressed_file_remaining': packed.exists()})
            assert outcome.returncode == 0 and remains == 0 and not packed.exists(), compressed_cases[-1]
        print(json.dumps({'cli_version':detected['version'],'automatic_lock_verification':'passed',
                          'locked_delete':'refused, rollout intact','unlocked_delete':'success, rollout removed',
                          'missing_rollout':'orphan metadata removed successfully',
                          'compressed_rollouts':compressed_cases,
                          'read_only_probe':'busy/free matches CLI','home':'isolated temporary directory'},ensure_ascii=False))


if __name__ == '__main__': main()
