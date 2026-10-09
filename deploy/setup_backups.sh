#!/usr/bin/env bash
# One-time setup of nightly backups on the server that runs a deployment.
#
#   sudo bash deploy/setup_backups.sh DEPLOY_DIR DEPLOY_USER
#
# Installs age, rclone and rsync, creates an SSH key for the backup mirror (printing the public half to give to
# deploy/setup_backup_mirror.sh on the other server), and installs a systemd timer that runs
# `deploy/backup.sh nightly` at about 02:30 UTC. Fill in DEPLOY_DIR/.backup.env first (deploy/backup.env.example).
set -euo pipefail

fail() { echo "Error: $*" >&2; exit 1; }
[[ $# -eq 2 ]] || { echo "Usage: sudo bash deploy/setup_backups.sh DEPLOY_DIR DEPLOY_USER" >&2; exit 2; }
[[ $EUID -eq 0 ]] || fail "Run this with sudo."
deploy_dir=$(cd "$1" && pwd); user=$2
id "$user" >/dev/null 2>&1 || fail "No user $user."
[[ -f $deploy_dir/.env.prod || -f $deploy_dir/.env.dev ]] || fail "$deploy_dir has no .env.prod or .env.dev."
[[ -f $deploy_dir/.backup.env ]] || fail "Create $deploy_dir/.backup.env from deploy/backup.env.example first."
chown "$user" "$deploy_dir/.backup.env"; chmod 600 "$deploy_dir/.backup.env"
id -nG "$user" | grep -qw docker || fail "$user must be in the docker group to dump the database."

apt-get update -qq
DEBIAN_FRONTEND=noninteractive apt-get install -y -qq age rclone rsync curl >/dev/null

home=$(getent passwd "$user" | cut -d: -f6)
key="$home/.ssh/tapline_idp_backup"
if [[ ! -f $key ]]; then
  install -d -m 700 -o "$user" -g "$user" "$home/.ssh"
  sudo -u "$user" ssh-keygen -q -t ed25519 -N '' -C "tapline-idp-backup@$(hostname)" -f "$key"
fi

cat > /etc/systemd/system/tapline-idp-backup.service <<EOF
[Unit]
Description=TapLine IDP nightly database backup
Wants=network-online.target
After=network-online.target docker.service

[Service]
Type=oneshot
User=$user
WorkingDirectory=$deploy_dir
ExecStart=/usr/bin/bash $deploy_dir/deploy/backup.sh nightly
EOF
cat > /etc/systemd/system/tapline-idp-backup.timer <<'EOF'
[Unit]
Description=Run the TapLine IDP backup nightly

[Timer]
OnCalendar=*-*-* 02:30:00 UTC
RandomizedDelaySec=15m
Persistent=true

[Install]
WantedBy=timers.target
EOF
systemctl daemon-reload
systemctl enable --now tapline-idp-backup.timer

echo
echo "Nightly backups are scheduled:"
systemctl list-timers tapline-idp-backup.timer --no-pager | head -2
echo
echo "Mirror key (give this line to setup_backup_mirror.sh on the other server, and set"
echo "BACKUP_MIRROR_SSH_KEY=$key in .backup.env):"
cat "$key.pub"
echo
echo "When the mirror and bucket are ready, run a backup now and read its result:"
echo "  sudo systemctl start tapline-idp-backup.service && journalctl -u tapline-idp-backup.service -n 5 --no-pager"
