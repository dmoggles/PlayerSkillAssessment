#!/usr/bin/env bash
# Undo deploy/harden_host.sh on this server.
#
#   sudo bash deploy/unharden_host.sh
#
# - SSH: removes the script's settings file, so passwords and root login are back to how they were before.
# - Firewall: switched off. Its rules are kept, so `sudo ufw enable` turns the same set back on.
# - fail2ban: stopped and no longer started at boot (any bans end with it).
# - Automatic updates: the script's reboot settings are removed. Security updates stay on, as on a stock
#   Ubuntu server; `sudo dpkg-reconfigure -plow unattended-upgrades` turns them off.
# Packages stay installed. If SSH is locked out, run this from your hosting provider's web console.
set -euo pipefail

fail() { echo "Error: $*" >&2; exit 1; }
[[ $EUID -eq 0 ]] || fail "Run this with sudo."
ssh_conf=/etc/ssh/sshd_config.d/10-tapline-idp.conf
upgrades_conf=/etc/apt/apt.conf.d/52tapline-idp-upgrades

echo "This will, on $(hostname):"
echo "  - restore the SSH settings from before harden_host.sh"
echo "  - switch the firewall off (its rules are kept)"
echo "  - stop fail2ban"
echo "  - remove the automatic-reboot settings (security updates stay on)"
read -r -p "Type yes to continue: " answer
[[ $answer == yes ]] || { echo "Nothing changed."; exit 1; }

if [[ -f $ssh_conf ]]; then
  backup=$(mktemp)
  cp "$ssh_conf" "$backup"
  rm -f "$ssh_conf"
  if ! sshd -t; then
    cp "$backup" "$ssh_conf"; rm -f "$backup"
    fail "Without the hardening file the SSH configuration doesn't validate; put it back and changed nothing for SSH."
  fi
  rm -f "$backup"
  systemctl reload ssh 2>/dev/null || systemctl reload sshd
  echo "SSH: settings from before harden_host.sh restored."
else
  echo "SSH: no hardening settings found; unchanged."
fi

if command -v ufw >/dev/null; then ufw disable >/dev/null; echo "Firewall: off (rules kept; 'sudo ufw enable' restores them)."; fi
if systemctl list-unit-files fail2ban.service >/dev/null 2>&1; then systemctl disable --now fail2ban >/dev/null 2>&1 || true; echo "fail2ban: stopped."; fi
rm -f "$upgrades_conf"
echo "Automatic reboots: off. Security updates: still on."
echo
echo "Done. Check SSH from a second terminal before closing this session."
