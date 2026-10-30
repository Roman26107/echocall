import json
import os
import socket

from shared.internal_api.operations import remote_operation


VALID_BACKUP_TARGETS = {'foreign', 'google', 'all'}
BACKUP_TRIGGER_SOCKET = os.getenv(
    'BACKUP_TRIGGER_SOCKET',
    '/run/echocall-backup-trigger/trigger.sock',
).strip()
BACKUP_TRIGGER_TIMEOUT = float(os.getenv('BACKUP_TRIGGER_TIMEOUT', '3'))


class BackupTriggerError(RuntimeError):
    pass


def _trigger_request(payload: dict) -> dict:
    raw = json.dumps(payload, separators=(',', ':')).encode('utf-8') + b'\n'
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
            client.settimeout(BACKUP_TRIGGER_TIMEOUT)
            client.connect(BACKUP_TRIGGER_SOCKET)
            client.sendall(raw)
            response = bytearray()
            while len(response) <= 64 * 1024:
                chunk = client.recv(4096)
                if not chunk:
                    break
                response.extend(chunk)
    except (OSError, TimeoutError) as error:
        raise BackupTriggerError('Сервис запуска резервных копий недоступен') from error
    try:
        result = json.loads(response.decode('utf-8'))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise BackupTriggerError('Сервис резервных копий вернул некорректный ответ') from error
    if not isinstance(result, dict) or result.get('ok') is not True:
        raise BackupTriggerError('Не удалось выполнить команду резервного копирования')
    return result


@remote_operation('backups.start', mutating=True)
def start_backup(session, target: str) -> dict:
    if not isinstance(target, str) or target not in VALID_BACKUP_TARGETS:
        raise ValueError('Invalid backup target')
    return _trigger_request({'action': 'start', 'target': target})


@remote_operation('backups.status')
def get_backup_status(session) -> dict:
    return _trigger_request({'action': 'status'})['status']
