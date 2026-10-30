import importlib.util
import socket
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from shared.services.backups import start_backup


ROOT = Path(__file__).resolve().parents[1]
TRIGGER_PATH = ROOT / 'scripts' / 'backup' / 'echocall-backup-trigger.py'


def load_trigger_module():
    spec = importlib.util.spec_from_file_location('echocall_backup_trigger', TRIGGER_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError('Unable to load backup trigger module')
    module = importlib.util.module_from_spec(spec)
    with patch.object(socket, 'AF_UNIX', 1, create=True):
        spec.loader.exec_module(module)
    return module


class BackupServiceTests(unittest.TestCase):
    def test_service_rejects_non_allowlisted_target_before_socket_call(self):
        with patch('shared.services.backups._trigger_request') as request:
            with self.assertRaises(ValueError):
                start_backup(object(), 'unit;reboot')
        request.assert_not_called()

    def test_trigger_maps_target_to_fixed_systemd_unit(self):
        trigger = load_trigger_module()
        controller = trigger.BackupController()
        with patch.object(trigger.subprocess, 'run', return_value=Mock(returncode=0)) as run:
            controller._run('google')
        run.assert_called_once_with(
            ['systemctl', 'start', 'echocall-backup@google.service'],
            check=False,
            timeout=2 * 60 * 60,
        )
        self.assertEqual(controller.status()['state'], 'success')
        self.assertEqual(controller.status()['backends'], {'google': 'success'})

    def test_trigger_rejects_parallel_manual_backup(self):
        trigger = load_trigger_module()
        controller = trigger.BackupController()
        controller._status['state'] = 'running'
        controller._status['target'] = 'foreign'
        result = controller.start('google')
        self.assertFalse(result['accepted'])
        self.assertEqual(result['status']['target'], 'foreign')


if __name__ == '__main__':
    unittest.main()
