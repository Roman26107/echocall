#!/usr/bin/env python3
"""Minimal root-side broker for manually starting approved backup units."""

import json
import os
import socket
import socketserver
import subprocess
import threading
from datetime import datetime, timezone
from pathlib import Path


SOCKET_PATH = Path('/run/echocall-backup-trigger/trigger.sock')
MAX_REQUEST_BYTES = 4096
TARGET_UNITS = {
    'foreign': ('echocall-backup@foreign.service',),
    'google': ('echocall-backup@google.service',),
    'all': (
        'echocall-backup@foreign.service',
        'echocall-backup@google.service',
    ),
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class BackupController:
    def __init__(self):
        self._lock = threading.Lock()
        self._status = {
            'state': 'idle',
            'target': None,
            'started_at': None,
            'finished_at': None,
            'backends': {},
        }

    def status(self) -> dict:
        with self._lock:
            return json.loads(json.dumps(self._status))

    def start(self, target: str) -> dict:
        if target not in TARGET_UNITS:
            return {'ok': False, 'error': 'invalid_target'}
        with self._lock:
            if self._status['state'] == 'running':
                return {'ok': True, 'accepted': False, 'status': self.status_unlocked()}
            backends = {
                unit.split('@', 1)[1].split('.', 1)[0]: 'pending'
                for unit in TARGET_UNITS[target]
            }
            self._status = {
                'state': 'running',
                'target': target,
                'started_at': _now(),
                'finished_at': None,
                'backends': backends,
            }
            response = self.status_unlocked()
        threading.Thread(target=self._run, args=(target,), daemon=True).start()
        return {'ok': True, 'accepted': True, 'status': response}

    def status_unlocked(self) -> dict:
        return json.loads(json.dumps(self._status))

    def _run(self, target: str) -> None:
        failed = False
        for unit in TARGET_UNITS[target]:
            backend = unit.split('@', 1)[1].split('.', 1)[0]
            with self._lock:
                self._status['backends'][backend] = 'running'
            try:
                result = subprocess.run(
                    ['systemctl', 'start', unit],
                    check=False,
                    timeout=2 * 60 * 60,
                )
                state = 'success' if result.returncode == 0 else 'failed'
            except (OSError, subprocess.TimeoutExpired):
                state = 'failed'
            failed = failed or state == 'failed'
            with self._lock:
                self._status['backends'][backend] = state
        with self._lock:
            self._status['state'] = 'failed' if failed else 'success'
            self._status['finished_at'] = _now()


CONTROLLER = BackupController()


class TriggerHandler(socketserver.StreamRequestHandler):
    def handle(self) -> None:
        raw = self.rfile.readline(MAX_REQUEST_BYTES + 1)
        if len(raw) > MAX_REQUEST_BYTES:
            self._reply({'ok': False, 'error': 'request_too_large'})
            return
        try:
            request = json.loads(raw.decode('utf-8'))
        except (UnicodeDecodeError, json.JSONDecodeError):
            self._reply({'ok': False, 'error': 'invalid_json'})
            return
        action = request.get('action') if isinstance(request, dict) else None
        if action == 'status':
            self._reply({'ok': True, 'status': CONTROLLER.status()})
        elif action == 'start':
            self._reply(CONTROLLER.start(request.get('target', '')))
        else:
            self._reply({'ok': False, 'error': 'invalid_action'})

    def _reply(self, payload: dict) -> None:
        self.wfile.write(json.dumps(payload, separators=(',', ':')).encode('utf-8') + b'\n')


class TriggerServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
    address_family = getattr(socket, 'AF_UNIX')
    daemon_threads = True


def main() -> None:
    SOCKET_PATH.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    SOCKET_PATH.unlink(missing_ok=True)
    server = TriggerServer(str(SOCKET_PATH), TriggerHandler)
    os.chmod(SOCKET_PATH, 0o600)
    try:
        server.serve_forever()
    finally:
        server.server_close()
        SOCKET_PATH.unlink(missing_ok=True)


if __name__ == '__main__':
    main()
