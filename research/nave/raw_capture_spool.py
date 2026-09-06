"""Lossless durable capture primitive; no normalization, SQLite or research.

Deployment is deliberately separate from the existing prospective collector.
An acknowledgement means the raw record survived fsync, not that downstream
processing or a scientific day is complete. No automatic retention deletion.
"""
from __future__ import annotations

import base64
from datetime import UTC, datetime
import fcntl
import hashlib
import json
import os
from pathlib import Path
import shutil
from typing import Iterable


class SpoolIncomplete(RuntimeError):
    pass


class RawCaptureSpool:
    def __init__(self, root: Path, *, max_bytes: int, reserve_bytes: int,
                 segment_bytes: int = 64 * 1024 * 1024):
        if min(max_bytes, segment_bytes) <= 0 or reserve_bytes < 0:
            raise ValueError('Invalid bounded disk policy')
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.lock = (self.root / 'writer.lock').open('a')
        try:
            fcntl.flock(self.lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BaseException:
            self.lock.close()
            raise
        paths = sorted(self.root.glob('segment-*.jsonl'))
        self.used = sum(p.stat().st_size for p in paths)
        self.number = int(paths[-1].stem.split('-')[1]) + 1 if paths else 0
        self.max_bytes, self.reserve_bytes = max_bytes, reserve_bytes
        self.segment_bytes = segment_bytes
        self.handle = None
        self.path = None
        self.failed = False

    def append_batch(self, frames: Iterable[tuple[bytes, datetime]]) -> list[dict]:
        """Accept a caller-bounded batch, retaining the exact receive clock/bytes.

        Every supplied provider field is retained in raw_base64, including
        provider timestamp, participants, signatures, slots, pool and deployer.
        No parsing or canonicalization of provider data occurs here.
        """
        if self.failed:
            raise SpoolIncomplete('FAILED_WRITER_REQUIRES_RECONCILIATION')
        chunks, receipts = [], []
        total = 0
        for raw, received in frames:
            if not isinstance(raw, bytes) or received.tzinfo is None:
                raise ValueError('Raw bytes and timezone-aware receive clock required')
            if len(raw) > 8*1024*1024:
                raise SpoolIncomplete('CAPTURE_FRAME_EXCEEDS_BOUND')
            stamp = received.astimezone(UTC).isoformat()
            record = {'schema': 'nave.raw-capture.v1', 'received_at': stamp,
                      'available_at': stamp, 'event_id': hashlib.sha256(raw).hexdigest(),
                      'raw_base64': base64.b64encode(raw).decode('ascii')}
            line = (json.dumps(record, separators=(',', ':'))+'\n').encode()
            total += len(line)
            if total > self.segment_bytes:
                raise SpoolIncomplete('CAPTURE_BATCH_EXCEEDS_SEGMENT_BOUND')
            chunks.append(line)
            receipts.append({'event_id': record['event_id'], 'received_at': stamp})
        if not chunks:
            return []
        if self.used + total > self.max_bytes or shutil.disk_usage(self.root).free-total < self.reserve_bytes:
            raise SpoolIncomplete('CAPTURE_DISK_LIMIT_INCOMPLETE')
        try:
            if self.handle is None or self.handle.tell()+total > self.segment_bytes:
                if self.handle is not None:
                    self.handle.close()
                self.path = self.root / f'segment-{self.number:012d}.jsonl'
                self.number += 1
                self.handle = self.path.open('xb')
            for line, receipt in zip(chunks, receipts):
                receipt.update(segment=self.path.name, offset=self.handle.tell())
                self.handle.write(line)
                receipt['next_offset'] = self.handle.tell()
            self.handle.flush()
            os.fsync(self.handle.fileno())
            directory = os.open(self.root, os.O_RDONLY | os.O_DIRECTORY)
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
            self.used += total
            return receipts
        except BaseException:
            self.failed = True
            raise

    def close(self):
        if self.handle is not None:
            self.handle.close()
        self.lock.close()


def replay_segment(path: Path, *, offset: int = 0, max_line_bytes: int = 16*1024*1024):
    """Read captured evidence only; caller advances cursor AFTER durable dedupe.

    Replay must target sealed segments, not the writer's active segment. On
    crash, validate the tail before sealing; corruption never permits skipping.
    """
    with path.open('rb') as handle:
        if offset < 0 or offset > path.stat().st_size:
            raise SpoolIncomplete('INVALID_REPLAY_CURSOR')
        if offset:
            handle.seek(offset-1)
            if handle.read(1) != b'\n':
                raise SpoolIncomplete('UNALIGNED_REPLAY_CURSOR')
        handle.seek(offset)
        while line := handle.readline(max_line_bytes+1):
            if len(line) > max_line_bytes or not line.endswith(b'\n'):
                raise SpoolIncomplete('CORRUPT_OR_PARTIAL_CAPTURE_TAIL')
            try:
                record = json.loads(line)
                raw = base64.b64decode(record['raw_base64'], validate=True)
                stamp = datetime.fromisoformat(record['received_at'])
                valid = (record['schema'] == 'nave.raw-capture.v1' and stamp.tzinfo is not None
                         and record['available_at'] == record['received_at']
                         and hashlib.sha256(raw).hexdigest() == record['event_id'])
            except (KeyError, TypeError, ValueError) as error:
                raise SpoolIncomplete('CORRUPT_CAPTURE_RECORD') from error
            if not valid:
                raise SpoolIncomplete('CORRUPT_CAPTURE_IDENTITY_OR_CLOCK')
            yield raw, stamp, {'segment': path.name, 'next_offset': handle.tell(),
                               'event_id': record['event_id']}
