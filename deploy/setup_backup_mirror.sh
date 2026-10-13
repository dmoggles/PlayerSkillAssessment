#!/usr/bin/env bash
# One-time setup of the second server as a backup mirror. Safe to run again (e.g. with a new key).
#
#   sudo bash setup_backup_mirror.sh "ssh-ed25519 AAAA... tapline-idp-backup@prod"
#
# Creates the user idpbackup and /srv/tapline-idp-backups. The production server's key may only write new files
# there (rrsync -wo): it can't read anything. It can't change or delete backups either: a timer hands every
# arrived backup to root within a few minutes, in folders where idpbackup may only add files (sticky, root-owned).
# Newer rrsync versions also get -no-del. This server prunes old files itself, daily: daily/ after 35 days, the rest
# after 92 (deleted data must leave backups within about three months). Backups are encrypted, so this server can't
# read them.
set -euo pipefail

fail() { echo "Error: $*" >&2; exit 1; }
[[ $# -eq 1 && $1 == ssh-* ]] || { echo "Usage: sudo bash setup_backup_mirror.sh \"PUBLIC_KEY_LINE\"" >&2; exit 2; }
[[ $EUID -eq 0 ]] || fail "Run this with sudo."
key_blob=$(awk '{ print $2 }' <<< "$1")
[[ -n $key_blob ]] || fail "That doesn't look like an SSH public key line."
apt-get update -qq || true
DEBIAN_FRONTEND=noninteractive apt-get install -y -qq rsync >/dev/null
rrsync=$(command -v rrsync || true)
if [[ -z $rrsync && -f /usr/share/doc/rsync/scripts/rrsync.gz ]]; then  # older Ubuntu ships it only as an example
  gunzip -c /usr/share/doc/rsync/scripts/rrsync.gz > /usr/local/bin/rrsync && chmod 755 /usr/local/bin/rrsync
  rrsync=/usr/local/bin/rrsync
fi
[[ -n $rrsync ]] || fail "rrsync wasn't found (it comes with rsync)."
grep -q -- '-wo' "$rrsync" || fail "$rrsync doesn't support write-only mode (-wo); rsync 3.1 or newer is needed."
rrsync_options="-wo"
grep -q -- 'no-del' "$rrsync" && rrsync_options="-wo -no-del"

dir=/srv/tapline-idp-backups
id idpbackup >/dev/null 2>&1 || useradd --system --create-home --shell /bin/bash idpbackup
passwd -l idpbackup >/dev/null
# idpbackup may add files to these folders but, as they are root's and sticky, can't remove or rename files it
# doesn't own; the seal timer below makes every arrived backup root's.
install -d -m 0750 -o root -g idpbackup "$dir"
for sub in daily monthly pre-deploy pre-restore; do install -d -m 1770 -o root -g idpbackup "$dir/$sub"; done

home=$(getent passwd idpbackup | cut -d: -f6)
install -d -m 700 -o idpbackup -g idpbackup "$home/.ssh"
keys="$home/.ssh/authorized_keys"
touch "$keys"
# Replace any earlier line for this key (sshd uses the first match), then add the current one.
grep -vF -- "$key_blob" "$keys" > "$keys.new" || true
echo "command=\"$rrsync $rrsync_options $dir\",restrict $1" >> "$keys.new"
mv "$keys.new" "$keys"
chown idpbackup:idpbackup "$keys"; chmod 600 "$keys"

cat > /etc/systemd/system/tapline-idp-backup-seal.service <<EOF
[Unit]
Description=Hand arrived TapLine IDP backups to root, so the sending server can't change or delete them

[Service]
Type=oneshot
ExecStart=/usr/bin/find $dir -mindepth 2 -maxdepth 2 -type f -name '*.dump.age' ! -user root -exec chown root:root {} + -exec chmod 0440 {} +
EOF
cat > /etc/systemd/system/tapline-idp-backup-seal.timer <<'EOF'
[Unit]
Description=Seal arrived TapLine IDP backups every 5 minutes

[Timer]
OnCalendar=*:0/5
Persistent=true

[Install]
WantedBy=timers.target
EOF
cat > /etc/systemd/system/tapline-idp-backup-prune.service <<EOF
[Unit]
Description=Remove old TapLine IDP backups from the mirror

[Service]
Type=oneshot
ExecStart=/usr/bin/bash -c 'find $dir/daily -name "*.dump.age" -mtime +35 -delete; find $dir/pre-deploy $dir/pre-restore $dir/monthly -name "*.dump.age" -mtime +92 -delete; true'
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
systemctl enable --now tapline-idp-backup-seal.timer tapline-idp-backup-prune.timer >/dev/null 2>&1
echo "Mirror ready: backups land in $dir ($rrsync $rrsync_options; sealed every 5 minutes)."
echo "On the production server set BACKUP_MIRROR=idpbackup@$(hostname -f):"
