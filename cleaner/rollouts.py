"""Physical forms of a Codex rollout. Metadata may retain the pre-compression path."""
from pathlib import Path
import io

try:
    from compression.zstd import open as _zstd_open
except ImportError:
    try:
        import zstandard
    except ImportError:
        zstandard = None

    def _zstd_open(path, mode):
        if zstandard is None:
            return None
        return io.BufferedReader(zstandard.open(path, mode, dctx=zstandard.ZstdDecompressor(max_window_size=128 * 1024 * 1024)))


def compressed(path):
    return str(path).lower().endswith('.jsonl.zst')


def variants(path):
    path = Path(path)
    if compressed(path):
        return (Path(str(path)[:-4]), path)
    if path.suffix.lower() == '.jsonl':
        return (path, Path(str(path) + '.zst'))
    return (path,)


def present_variants(path):
    result = []
    for candidate in variants(path):
        try:
            candidate.stat()
        except FileNotFoundError:
            continue
        except OSError:
            # Keep inaccessible files for the scanner to report and block.
            pass
        result.append(candidate)
    return result


def header_line(path, limit):
    if not compressed(path):
        with Path(path).open('rb') as source:
            return source.readline(limit + 1)
    # Counting and database-path ownership do not require a decompressor.
    # Reading one byte still checks access when optional Zstandard support is absent.
    with Path(path).open('rb') as source:
        source.read(1)
    try:
        reader = _zstd_open(path, 'rb')
        if reader is None:
            return None
        with reader:
            return reader.readline(limit + 1)
    except Exception as error:
        raise OSError('压缩日志文件头无法读取：' + str(error)) from error
