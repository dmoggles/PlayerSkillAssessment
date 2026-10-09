#!/usr/bin/env bash
# Baseline hardening for an Ubuntu VPS that runs TapLine IDP. Run once per server, from an SSH session that
# logged in with a key, and keep that session open until you've checked a second login works.
#
#   sudo bash deploy/harden_host.sh
#
# - Firewall (ufw): only SSH, HTTP and HTTPS come in. The app's containers listen on 127.0.0.1 only.
# - Automatic security updates, with a reboot at 04:00 UTC when one needs it (after the 02:30 backup);
#   the containers start again by themselves.
# - SSH: keys only, no root login.
# - fail2ban: bans addresses that keep failing SSH logins.
set -euo pipefail

fail() { echo "Error: $*" >&2; exit 1; }
[[ $EUID -eq 0 ]] || fail "Run this with sudo."
admin=${SUDO_USER:-}
[[ -n $admin && $admin != root ]] || fail "Run this with sudo from your own (non-root) account, so it can check your SSH key."
home=$(getent passwd "$admin" | cut -d: -f6)
grep -qE '^(ssh|ecdsa)-' "$home/.ssh/authorized_keys" 2>/dev/null \
  || fail "$admin has no SSH key in $home/.ssh/authorized_keys. Add one before passwords are turned off."
ssh_port=$(sshd -T 2>/dev/null | awk '$1 == "port" { print $2; exit }')
ssh_port=${ssh_port:-22}

echo "This will, on $(hostname):"
echo "  - allow only SSH (port $ssh_port), HTTP and HTTPS through the firewall"
echo "  - install automatic security updates (reboot at 04:00 UTC when needed)"
echo "  - turn off SSH passwords and root login ($admin keeps key access)"
echo "  - install fail2ban for SSH"
read -r -p "Type yes to continue: " answer
[[ $answer == yes ]] || { echo "Nothing changed."; exit 1; }

apt-get update -qq
DEBIAN_FRONTEND=noninteractive apt-get install -y -qq ufw unattended-upgrades fail2ban >/dev/null

ufw default deny incoming >/dev/null
ufw default allow outgoing >/dev/null
ufw allow "$ssh_port/tcp" comment ssh >/dev/null
ufw allow 80/tcp comment http >/dev/null
ufw allow 443/tcp comment https >/dev/null
ufw --force enable >/dev/null

cat > /etc/apt/apt.conf.d/20auto-upgrades <<'EOF'
APT::Periodic::Update-Package-Lists "1";
APT::Periodic::Unattended-Upgrade "1";
EOF
cat > /etc/apt/apt.conf.d/52tapline-idp-upgrades <<'EOF'
Unattended-Upgrade::Automatic-Reboot "true";
Unattended-Upgrade::Automatic-Reboot-Time "04:00";
Unattended-Upgrade::Remove-Unused-Dependencies "true";
EOF

cat > /etc/ssh/sshd_config.d/10-tapline-idp.conf <<'EOF'
PasswordAuthentication no
KbdInteractiveAuthentication no
PermitRootLogin no
EOF
sshd -t || { rm -f /etc/ssh/sshd_config.d/10-tapline-idp.conf; fail "The SSH settings didn't validate; nothing changed for SSH."; }
systemctl reload ssh 2>/dev/null || systemctl reload sshd

systemctl enable --now fail2ban >/dev/null

echo
ufw status | head -8
echo
echo "Done. Before closing this session, open a NEW terminal and check you can still log in:"
echo "  ssh -p $ssh_port $admin@$(hostname -f)"
