# EchoCall PostgreSQL backups

## Architecture

- PostgreSQL stays private on RF and is exported with `pg_dump -Fc`.
- Restic encrypts every snapshot before it leaves RF.
- `foreign`: daily snapshots over a strict-host-key-checked, chrooted SFTP account.
- `google`: weekly snapshots through an `rclone` Google Drive remote.
- Retention defaults to 7 daily, 4 weekly, and 6 monthly snapshots per backend.
- Monthly restore tests use a temporary network-isolated PostgreSQL container.

Google Drive and foreign never receive PostgreSQL credentials or a plain data
volume. The restic password is the recovery key. Keep an offline copy in a
password manager: losing it makes all snapshots unrecoverable.

## Safe installation order

1. Generate a dedicated Ed25519 key on RF. Copy only the public key to foreign
   and run `scripts/backup/setup-foreign-repository.sh PUBLIC_KEY_FILE` as root.
   Never copy the private key away from RF.
2. Run `sudo scripts/backup/install-rf.sh` on RF. It installs tools and unit
   files but deliberately does not enable any timer.
3. Pin the foreign SSH host key in `/etc/echocall-backup/known_hosts`, review
   `/etc/echocall-backup/backup.env`, and create a mode-600
   `/etc/echocall-backup/restic-password` with a randomly generated value.
4. Initialize and validate foreign storage:

   ```bash
   sudo echocall-backup-init foreign
   sudo echocall-backup foreign
   sudo echocall-restore-test foreign
   sudo systemctl enable --now echocall-backup-foreign.timer \
     echocall-restore-test-foreign.timer
   ```

5. Create a dedicated Google OAuth **Desktop app** client for rclone and configure
   `google-drive` in `/etc/echocall-backup/rclone.conf` with `scope = drive.file`.
   Use your own OAuth client for the installation. Never share the Google password,
   2FA code, client secret, or OAuth token. Keep the config `root:root` mode 600.
   Verify the effective token scope with Google's `tokeninfo` endpoint; it must be
   `https://www.googleapis.com/auth/drive.file`, not full `drive` access. Then run:

   ```bash
   sudo echocall-backup-init google
   sudo echocall-backup google
   sudo echocall-restore-test google
   sudo systemctl enable --now echocall-backup-google.timer \
     echocall-restore-test-google.timer
   ```

   Enable the timers only after both manual commands complete successfully. If an
   existing remote uses a different OAuth client, re-authorize it with the
   dedicated client before enabling scheduled backups.

## Operations and recovery

The Telegram admin menu can request an immediate backup to `foreign`, `google`,
or both. The RF Internal API talks to a root-owned Unix socket exposed by
`echocall-backup-trigger.service`; it never receives the Docker socket and the
trigger accepts only the fixed systemd unit allowlist. The request returns
immediately and the admin screen polls status with «Обновить статус».

The application image uses UID/GID `10001:10001`, not root. The installer creates
the dedicated `echocall-backup` host group with GID 10001. The trigger runs as root
with that group, creates its runtime directory as `0750`, and exposes a `0660`
socket. The mount remains read-only and accepts only the fixed unit allowlist.
If GID 10001 is already assigned to another group, resolve that conflict before
installation rather than making the socket world-writable. Re-run the reviewed
installer when upgrading an older root-only socket installation.

Inspect schedules and logs:

```bash
systemctl list-timers 'echocall-*backup*' 'echocall-restore*'
journalctl -u echocall-backup@foreign.service --since today
```

For disaster recovery, install restic, provide the offline recovery password,
restore the latest `echocall.dump`, create an empty PostgreSQL database, and run
`pg_restore --clean --if-exists --no-owner --no-acl`. Always test on an isolated
database before replacing production.
