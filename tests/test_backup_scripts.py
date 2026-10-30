import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BACKUP = ROOT / 'scripts' / 'backup'


class BackupScriptTests(unittest.TestCase):
    def test_runtime_files_do_not_contain_windows_line_endings(self):
        runtime_files = (
            list(BACKUP.glob('*.sh'))
            + list(BACKUP.glob('*.py'))
            + [BACKUP / 'backup.env.example']
        )

        for path in runtime_files:
            with self.subTest(path=path.name):
                self.assertNotIn(b'\r', path.read_bytes())

    def test_dump_is_custom_format_and_does_not_expose_database_secret(self):
        script = (BACKUP / 'echocall-backup.sh').read_text(encoding='utf-8')

        self.assertIn('pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc', script)
        self.assertIn('--no-owner --no-acl', script)
        self.assertNotIn('POSTGRES_PASSWORD', script)
        self.assertIn('pg_restore --list', script)
        self.assertIn('trap cleanup EXIT INT TERM', script)

    def test_backups_are_encrypted_rotated_and_serialized(self):
        script = (BACKUP / 'echocall-backup.sh').read_text(encoding='utf-8')
        library = (BACKUP / 'echocall-backup-lib.sh').read_text(encoding='utf-8')

        self.assertIn('RESTIC_PASSWORD_FILE', library)
        self.assertIn('must be owned by root', library)
        self.assertIn('regular non-symlink file', library)
        self.assertIn('flock -n', library)
        self.assertIn('StrictHostKeyChecking=yes', library)
        self.assertIn('forget', script)
        self.assertIn('--keep-daily', script)
        self.assertIn('--keep-weekly', script)
        self.assertIn('--keep-monthly', script)
        self.assertIn('--prune', script)

    def test_restore_test_uses_isolated_ephemeral_postgres(self):
        script = (BACKUP / 'echocall-restore-test.sh').read_text(encoding='utf-8')

        self.assertIn('--network none', script)
        self.assertIn('postgres:16-alpine', script)
        self.assertIn('PostgreSQL init process complete', script)
        self.assertIn('temporary PostgreSQL initialization timed out', script)
        self.assertIn('pg_restore', script)
        self.assertIn('--exit-on-error', script)
        self.assertIn('docker rm -f', script)
        self.assertIn("schemaname = 'public'", script)

    def test_foreign_account_is_chrooted_and_sftp_only(self):
        script = (BACKUP / 'setup-foreign-repository.sh').read_text(
            encoding='utf-8'
        )

        self.assertIn('ChrootDirectory /srv/echocall-backup', script)
        self.assertIn('ForceCommand internal-sftp', script)
        self.assertIn('PasswordAuthentication no', script)
        self.assertIn('AllowTcpForwarding no', script)
        self.assertIn('groupadd --system', script)
        self.assertIn('chmod 644 "$KEY_DIR/$BACKUP_USER"', script)
        self.assertIn('chown root:root "$KEY_DIR/$BACKUP_USER"', script)
        self.assertIn('sshd -t', script)

    def test_install_does_not_enable_timers_before_validation(self):
        script = (BACKUP / 'install-rf.sh').read_text(encoding='utf-8')

        self.assertIn('systemctl daemon-reload', script)
        self.assertIn("tr -d '\\r'", script)
        self.assertIn('systemctl enable --now echocall-backup-trigger.service', script)
        self.assertNotIn('enable --now echocall-backup-foreign.timer', script)
        self.assertNotIn('enable --now echocall-backup-google.timer', script)

    def test_trigger_allows_only_fixed_systemd_units(self):
        script = (BACKUP / 'echocall-backup-trigger.py').read_text(encoding='utf-8')
        self.assertIn("'foreign': ('echocall-backup@foreign.service',)", script)
        self.assertIn("'google': ('echocall-backup@google.service',)", script)
        self.assertIn("['systemctl', 'start', unit]", script)
        self.assertNotIn('shell=True', script)
        self.assertIn("os.chmod(SOCKET_PATH, 0o660)", script)
        unit = (BACKUP / 'systemd/echocall-backup-trigger.service').read_text(encoding='utf-8')
        self.assertIn('Group=echocall-backup', unit)
        self.assertIn('RuntimeDirectoryMode=0750', unit)
        self.assertIn('groupadd --system --gid 10001 echocall-backup',
                      (BACKUP / 'install-rf.sh').read_text(encoding='utf-8'))


if __name__ == '__main__':
    unittest.main()
