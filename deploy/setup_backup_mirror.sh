#!/usr/bin/env bash
# One-time setup of the second server as a backup mirror.
#
#   sudo bash setup_backup_mirror.sh "ssh-ed25519 AAAA... tapline-idp-backup@prod"
#
# Creates the user idpbackup and /srv/tapline-idp-backups. The production server's key may only write new files
# there (rrsync -wo -no-del): it can't read, change or delete backups, so a compromised production server can't
# destroy this copy. This server prunes old files itself, daily: daily/ after 35 days, pre-deploy/ and
# pre-restore/ after 120, monthly/ after 400. Backups are encrypted, so this server can't read them either.
set -euo pipefail

fail() { echo "Error: $*" >&2; exit 1; }
[[ $# -eq 1 && $1 == ssh-* ]] || { echo "Usage: sudo bash setup_backup_mirror.sh \"PUBLIC_KEY_LINE\"" >&2; exit 2; }
[[ $EUID -eq 0 ]] || fail "Run this with sudo."
apt-get update -qq
DEBIAN_FRONTEND=noninteractive apt-get install -y -qq rsync >/dev/null
rrsync=$(command -v rrsync) || fail "rrsync wasn't found; it ships with rsync 3.2.3 or later."

dir=/srv/tapline-idp-backups
id idpbackup >/dev/null 2>&1 || useradd --system --create-home --shell /bin/bash idpbackup
passwd -l idpbackup >/dev/null
install -d -m 700 -o idpbackup -g idpbackup "$dir"
home=$(getent passwd idpbackup | cut -d: -f6)
install -d -m 700 -o idpbackup -g idpbackup "$home/.ssh"
line="command=\"$rrsync -wo -no-del $dir\",restrict $1"
touch "$home/.ssh/authorized_keys"
grep -qxF "$line" "$home/.ssh/authorized_keys" || echo "$line" >> "$home/.ssh/authorized_keys"
chown idpbackup:idpbackup "$home/.ssh/authorized_keys"; chmod 600 "$home/.ssh/authorized_keys"

cat > /etc/systemd/system/tapline-idp-backup-prune.service <<EOF
[Unit]
Description=Remove old TapLine IDP backups from the mirror

[Service]
Type=oneshot
User=idpbackup
ExecStart=/usr/bin/bash -c 'find $dir/daily -name "*.dump.age" -mtime +35 -delete 2>/dev/null; find $dir/pre-deploy $dir/pre-restore -name "*.dump.age" -mtime +120 -delete 2>/dev/null; find $dir/monthly -name "*.dump.age" -mtime +400 -delete 2>/dev/null; true'
EOF
cat > /etc/systemd/system/tapline-idp-backup-prune.timer <<'EOF'
[Unit]
Description=Prune old TapLine IDP backups daily

[Timer]
OnCalendar=daily
Persistent=true

[Install]
WantedBy=timers.target
EOF
systemctl daemon-reload
systemctl enable --now tapline-idp-backup-prune.timer
echo "Mirror ready: backups land in $dir. On the production server set BACKUP_MIRROR=idpbackup@$(hostname -f):"
