#!/usr/bin/env bash
# Baseline hardening for an Ubuntu VPS that runs TapLine IDP. Run once per server, from an SSH session that
# logged in with a key, and keep that session open until you've checked a second login works.
#
#   sudo bash deploy/harden_host.sh [--allow PORT,PORT,...] [--password-login USER,USER,...] [--reboot]
#
# - Firewall (ufw): only SSH, HTTP, HTTPS and any --allow ports come in. The app's containers listen on
#   127.0.0.1 only. Use --allow for other services on the same server that are reached directly (e.g. 3306).
# - Automatic security updates. With --reboot, also a reboot at 04:00 UTC when an update needs one (after the
#   02:30 backup); only use it if everything on the server starts again by itself after a reboot.
# - SSH: keys only, no root login. --password-login keeps password login for named users that still need it
#   (fail2ban then guards them); move them to keys when you can.
# - fail2ban: bans addresses that keep failing SSH logins.
set -euo pipefail

fail() { echo "Error: $*" >&2; exit 1; }
extra_ports=(); password_users=(); reboot=false
while [[ $# -gt 0 ]]; do
  case $1 in
    --allow) [[ ${2:-} =~ ^[0-9]+(,[0-9]+)*$ ]] || fail "--allow takes ports separated by commas, e.g. --allow 3306,9100"
             IFS=, read -r -a extra_ports <<< "$2"; shift 2 ;;
    --password-login) [[ ${2:-} =~ ^[a-z_][a-z0-9_-]*(,[a-z_][a-z0-9_-]*)*$ ]] || fail "--password-login takes user names separated by commas"
             IFS=, read -r -a password_users <<< "$2"; shift 2 ;;
    --reboot) reboot=true; shift ;;
    *) fail "Unknown option $1. Usage: sudo bash deploy/harden_host.sh [--allow PORT,PORT,...] [--password-login USER,...] [--reboot]" ;;
  esac
done
[[ $EUID -eq 0 ]] || fail "Run this with sudo."
admin=${SUDO_USER:-}
[[ -n $admin && $admin != root ]] || fail "Run this with sudo from your own (non-root) account, so it can check your SSH key."
home=$(getent passwd "$admin" | cut -d: -f6)
grep -qE '^(ssh|ecdsa)-' "$home/.ssh/authorized_keys" 2>/dev/null \
  || fail "$admin has no SSH key in $home/.ssh/authorized_keys. Add one before passwords are turned off."
ssh_port=$(sshd -T 2>/dev/null | awk '$1 == "port" { print $2; exit }')
ssh_port=${ssh_port:-22}
for user in "${password_users[@]}"; do id "$user" >/dev/null 2>&1 || fail "No user $user (from --password-login)."; done
[[ ! " ${password_users[*]} " =~ " root " ]] || fail "Root login is turned off; don't list root in --password-login."

echo "This will, on $(hostname):"
echo "  - allow only SSH (port $ssh_port), HTTP, HTTPS${extra_ports[*]:+ and ports ${extra_ports[*]}} through the firewall; everything else is blocked"
if [[ $reboot == true ]]; then echo "  - install automatic security updates, rebooting at 04:00 UTC when one needs it"
else echo "  - install automatic security updates (no automatic reboots; reboot by hand when one asks)"; fi
echo "  - turn off SSH passwords and root login ($admin keeps key access${password_users[*]:+; password login stays for ${password_users[*]}})"
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
for port in "${extra_ports[@]}"; do ufw allow "$port/tcp" comment "kept open by harden_host.sh" >/dev/null; done
ufw --force enable >/dev/null

cat > /etc/apt/apt.conf.d/20auto-upgrades <<'EOF'
APT::Periodic::Update-Package-Lists "1";
APT::Periodic::Unattended-Upgrade "1";
EOF
cat > /etc/apt/apt.conf.d/52tapline-idp-upgrades <<EOF
Unattended-Upgrade::Automatic-Reboot "$reboot";
Unattended-Upgrade::Automatic-Reboot-Time "04:00";
Unattended-Upgrade::Remove-Unused-Dependencies "true";
EOF

ssh_conf=/etc/ssh/sshd_config.d/10-tapline-idp.conf
{
  echo "PasswordAuthentication no"
  echo "KbdInteractiveAuthentication no"
  echo "PermitRootLogin no"
  if [[ ${#password_users[@]} -gt 0 ]]; then
    echo "Match User $(IFS=,; echo "${password_users[*]}")"
    echo "    PasswordAuthentication yes"
    # Ends the Match, so settings that follow this file stay global.
    echo "Match all"
  fi
} > "$ssh_conf"
sshd -t || { rm -f "$ssh_conf"; fail "The SSH settings didn't validate; nothing changed for SSH."; }
# Check the result as sshd sees it, before reloading.
setting() { sshd -T -C "user=$1,host=check,addr=192.0.2.1" | awk '$1 == "passwordauthentication" { print $2 }'; }
[[ $(setting "$admin") == no ]] \
  || { rm -f "$ssh_conf"; fail "Another SSH setting keeps passwords on for $admin (see /etc/ssh/sshd_config and sshd_config.d); nothing changed for SSH."; }
for user in "${password_users[@]}"; do
  [[ $(setting "$user") == yes ]] || { rm -f "$ssh_conf"; fail "Password login for $user didn't take effect; nothing changed for SSH."; }
done
systemctl reload ssh 2>/dev/null || systemctl reload sshd

systemctl enable --now fail2ban >/dev/null

echo
ufw status | head -8
echo
echo "Done. Before closing this session, open a NEW terminal and check you can still log in:"
echo "  ssh -p $ssh_port $admin@$(hostname -f)"
