"""Windows writer-lock probes and isolated CLI compatibility verification.

Live lock files are never created, changed or removed. A shared nonblocking
byte-range probe conflicts with the exclusive lock held by Rust
std::fs::File::try_lock. This is a snapshot only; the official CLI acquires the
final exclusive lock. Compatibility checks use disposable temporary files.
"""
import ctypes
import json
import os
import subprocess
import tempfile
import uuid
from ctypes import wintypes
from pathlib import Path


def verify_cli_protocol(cli, version, runner):
    """Exercise the selected CLI against disposable sessions, never the real home.

    A compatible CLI must refuse the held writer lock, delete an independent
    session while that lock is held, then delete the protected session only
    after release. The caller supplies a runner with an isolated environment.
    """
    if os.name != 'nt':
        return {'verified': False, 'message': '只读：会话锁检测目前仅支持 Windows'}
    import msvcrt

    try:
        with tempfile.TemporaryDirectory(prefix='cleaner-lock-check-') as temporary:
            home = Path(temporary).resolve()
            sessions = home / 'sessions'
            sessions.mkdir()
            locked_id, idle_id = str(uuid.uuid4()), str(uuid.uuid4())
            paths = {}
            for sid in (locked_id, idle_id):
                path = sessions / f'rollout-2026-01-01T00-00-00-{sid}.jsonl'
                path.write_text(json.dumps({'timestamp': '2026-01-01T00:00:00Z',
                    'type': 'session_meta', 'payload': {'id': sid,
                    'timestamp': '2026-01-01T00:00:00Z', 'cwd': str(home),
                    'originator': 'codex_cli_rs', 'cli_version': version.removeprefix('codex-cli '),
                    'source': 'cli', 'model_provider': 'openai'}}) + '\n', encoding='utf-8')
                paths[sid] = path
            original = paths[locked_id].read_bytes()
            locks = home / 'thread-writer-locks'
            locks.mkdir()
            lock = locks / f'{locked_id}.lock'
            lock.touch()
            with lock.open('r+b') as held:
                msvcrt.locking(held.fileno(), msvcrt.LK_NBLCK, 1)
                try:
                    if probe_file(lock) != 'busy':
                        raise ValueError('无法检测临时会话的写入锁')
                    blocked = runner([cli, 'delete', '--force', locked_id], home)
                    if blocked.returncode == 0 or not paths[locked_id].is_file() or paths[locked_id].read_bytes() != original:
                        raise ValueError('CLI 未保护持有写入锁的临时会话')
                    idle = runner([cli, 'delete', '--force', idle_id], home)
                    if idle.returncode != 0 or paths[idle_id].exists():
                        raise ValueError('CLI 无法删除未占用的临时会话')
                    if not paths[locked_id].is_file() or paths[locked_id].read_bytes() != original or probe_file(lock) != 'busy':
                        raise ValueError('CLI 未保护持有写入锁的临时会话')
                finally:
                    held.seek(0)
                    msvcrt.locking(held.fileno(), msvcrt.LK_UNLCK, 1)
            if probe_file(lock) != 'free':
                raise ValueError('无法检测临时会话的写入锁')
            released = runner([cli, 'delete', '--force', locked_id], home)
            if released.returncode != 0 or paths[locked_id].exists():
                raise ValueError('CLI 无法删除释放写入锁后的临时会话')
            if not (locks / '.coordination.lock').is_file():
                raise ValueError('CLI 未生成预期的会话锁协调文件')
        return {'verified': True, 'message': '删除能力与会话锁检测已验证'}
    except (OSError, ValueError, subprocess.TimeoutExpired) as error:
        return {'verified': False, 'message': '只读：CLI 会话锁验证失败，删除已禁用。' + str(error)}


def probe_file(path):
    """Return free, busy, missing, or unknown. Never opens with write access."""
    if os.name != 'nt':
        return 'unknown'
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)

    class Overlapped(ctypes.Structure):
        _fields_ = [('Internal', ctypes.c_size_t), ('InternalHigh', ctypes.c_size_t),
                    ('Offset', wintypes.DWORD), ('OffsetHigh', wintypes.DWORD),
                    ('hEvent', wintypes.HANDLE)]

    kernel.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
                                  ctypes.c_void_p, wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
    kernel.CreateFileW.restype = wintypes.HANDLE
    kernel.LockFileEx.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.DWORD,
                                 wintypes.DWORD, wintypes.DWORD, ctypes.POINTER(Overlapped)]
    kernel.UnlockFileEx.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.DWORD,
                                   wintypes.DWORD, ctypes.POINTER(Overlapped)]
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    handle = kernel.CreateFileW(str(path), 0x80000000, 7, None, 3, 0x80, None)
    if handle == ctypes.c_void_p(-1).value:
        return 'missing' if ctypes.get_last_error() in (2, 3) else 'unknown'
    try:
        ov = Overlapped()
        if not kernel.LockFileEx(handle, 1, 0, 0xffffffff, 0xffffffff, ctypes.byref(ov)):
            return 'busy' if ctypes.get_last_error() == 33 else 'unknown'
        kernel.UnlockFileEx(handle, 0, 0xffffffff, 0xffffffff, ctypes.byref(ov))
        return 'free'
    finally:
        kernel.CloseHandle(handle)


def thread_activity(home, sid, protocol_verified):
    if protocol_verified is not True:
        return {'code': 'unknown', 'label': '状态未确认', 'reason': 'CLI 会话锁验证未通过，删除已禁用；请查看顶部 CLI 状态及设置中的连接详情'}
    root = Path(home) / 'thread-writer-locks'
    try:
        if not root.is_dir() or root.is_symlink() or root.resolve().parent != Path(home).resolve():
            raise OSError('writer-lock namespace unavailable')
        marker = root / '.coordination.lock'
        if marker.is_symlink() or not marker.is_file() or marker.resolve().parent != root.resolve():
            raise OSError('coordination marker absent')
        path = root / f'{sid}.lock'
        if path.is_symlink() or path.resolve().parent != root.resolve():
            raise OSError('writer-lock path outside namespace')
        status = probe_file(path)
    except OSError:
        status = 'unknown'
    if status == 'busy':
        return {'code': 'busy', 'label': '占用中', 'reason': '该会话仍被 Codex 持有写入锁；请先释放这个会话，无需关闭其他会话'}
    if status in ('free', 'missing'):
        return {'code': 'idle', 'label': '未占用', 'reason': ''}
    return {'code': 'unknown', 'label': '状态未确认', 'reason': '无法读取该会话的写入锁，暂不允许删除该目标'}
