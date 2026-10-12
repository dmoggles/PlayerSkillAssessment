#!/usr/bin/env bash
# Baseline hardening for an Ubuntu VPS that runs TapLine IDP. Run once per server, from an SSH session that
# logged in with a key, and keep that session open until you've checked a second login works.
#
#   sudo bash deploy/harden_host.sh [--allow PORT,PORT,...] [--password-login USER,USER,...] [--keep-ssh-passwords] [--reboot]
#
# - Firewall (ufw): only SSH, HTTP, HTTPS and any --allow ports come in. The app's containers listen on
#   127.0.0.1 only. Use --allow for other services on the same server that are reached directly (e.g. 3306).
# - Automatic security updates. With --reboot, also a reboot at 04:00 UTC when an update needs one (after the
#   02:30 backup); only use it if everything on the server starts again by itself after a reboot.
# - SSH: keys only, no root login. --password-login keeps password login for named users that still need it
#   (fail2ban then guards them); move them to keys when you can. Passwords are only turned off for you once
#   the server's login log shows you signing in with a key. --keep-ssh-passwords leaves SSH settings alone.
# - fail2ban: bans addresses that keep failing SSH logins.
#
# Everything is checked before anything changes: the SSH port(s) are found from the running server (never
# guessed), and the new SSH settings are validated before the firewall goes on. deploy/unharden_host.sh undoes it.
set -euo pipefail

fail() { echo "Error: $*" >&2; exit 1; }
changed=false
# No silent exits: say which step stopped the script, and whether anything had changed by then.
trap 'echo "Error: stopped at line $LINENO while running: $BASH_COMMAND" >&2
      if [[ $changed == true ]]; then echo "Some changes were already made; sudo bash unharden_host.sh undoes them." >&2
      else echo "Nothing was changed." >&2; fi' ERR

extra_ports=(); password_users=(); reboot=false; harden_ssh=true
while [[ $# -gt 0 ]]; do
  case $1 in
    --allow) [[ ${2:-} =~ ^[0-9]+(,[0-9]+)*$ ]] || fail "--allow takes ports separated by commas, e.g. --allow 3306,9100"
             IFS=, read -r -a extra_ports <<< "$2"; shift 2 ;;
    --password-login) [[ ${2:-} =~ ^[a-z_][a-z0-9_-]*(,[a-z_][a-z0-9_-]*)*$ ]] || fail "--password-login takes user names separated by commas"
             IFS=, read -r -a password_users <<< "$2"; shift 2 ;;
    --keep-ssh-passwords) harden_ssh=false; shift ;;
    --reboot) reboot=true; shift ;;
    *) fail "Unknown option $1. Usage: sudo bash harden_host.sh [--allow PORT,PORT,...] [--password-login USER,USER,...] [--keep-ssh-passwords] [--reboot]" ;;
  esac
done
[[ $EUID -eq 0 ]] || fail "Run this with sudo."
admin=${SUDO_USER:-}
[[ -n $admin && $admin != root ]] || fail "Run this with sudo from your own (non-root) account, so it can check your SSH key."
home=$(getent passwd "$admin" | cut -d: -f6)
if [[ $harden_ssh == true ]]; then
  grep -qE '^(ssh|ecdsa)-' "$home/.ssh/authorized_keys" 2>/dev/null \
    || fail "$admin has no SSH key in $home/.ssh/authorized_keys. Add one before passwords are turned off, or use --keep-ssh-passwords."
  # A key in authorized_keys isn't proof you log in with it: look for a recent key login in the SSH log.
  key_login=$( { zgrep -h "Accepted publickey for $admin " /var/log/auth.log* 2>/dev/null || true
                 journalctl -q --since "-30 days" _COMM=sshd 2>/dev/null | grep "Accepted publickey for $admin " || true; } | tail -1)
  [[ -n $key_login ]] || fail "The SSH log shows no key login for $admin in the last month, so turning passwords off could lock you out. Log in once with your key (ssh -o PasswordAuthentication=no ...) and run this again, or use --keep-ssh-passwords."
fi
for user in "${password_users[@]}"; do id "$user" >/dev/null 2>&1 || fail "No user $user (from --password-login)."; done
[[ ! " ${password_users[*]} " =~ " root " ]] || fail "Root login is turned off; don't list root in --password-login."
command -v sshd >/dev/null || fail "sshd isn't installed here."

# sshd's checks need this directory; Ubuntu only creates it when the SSH service starts.
install -d -m 0755 /run/sshd

# The ports SSH listens on: its settings, the running sshd, and systemd's ssh.socket (newer Ubuntu).
ssh_ports=$( {
  sshd -T 2>/dev/null | awk '$1 == "port" { print $2 }' || true
  ss -Htlnp 2>/dev/null | awk '/"sshd"/ { n = split($4, a, ":"); print a[n] }' || true
  if systemctl is-active --quiet ssh.socket 2>/dev/null; then
    systemctl show ssh.socket -p Listen --value 2>/dev/null | grep -oE ':[0-9]+ ' | tr -d ': ' || true
  fi
} | sort -un | tr '\n' ' ')
ssh_ports=${ssh_ports% }
[[ -n $ssh_ports ]] || fail "Couldn't work out which port SSH listens on, so the firewall can't safely be turned on. Nothing was changed."

echo "This will, on $(hostname):"
echo "  - allow only SSH (port ${ssh_ports// /, }), HTTP, HTTPS${extra_ports[*]:+ and ports ${extra_ports[*]}} through the firewall; everything else is blocked"
if [[ $reboot == true ]]; then echo "  - install automatic security updates, rebooting at 04:00 UTC when one needs it"
else echo "  - install automatic security updates (no automatic reboots; reboot by hand when one asks)"; fi
if [[ $harden_ssh == true ]]; then
  echo "  - turn off SSH passwords and root login ($admin keeps key access${password_users[*]:+; password login stays for ${password_users[*]}})"
else
  echo "  - leave SSH settings as they are (passwords stay on)"
fi
echo "  - install fail2ban for SSH"
read -r -p "Type yes to continue: " answer
[[ $answer == yes ]] || { echo "Nothing changed."; exit 1; }

if [[ $harden_ssh == true ]]; then
  # 1. SSH settings, written and checked first; sshd only picks them up at the reload further down.
  echo "Checking the new SSH settings…"
  ssh_conf=/etc/ssh/sshd_config.d/10-tapline-idp.conf
  [[ -d /etc/ssh/sshd_config.d ]] && grep -qiE '^\s*Include\s+/etc/ssh/sshd_config.d/' /etc/ssh/sshd_config \
    || fail "/etc/ssh/sshd_config doesn't include sshd_config.d, so these settings wouldn't apply. Nothing was changed."
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
  sshd -t || { rm -f "$ssh_conf"; fail "The SSH settings didn't validate. Nothing was changed."; }
  setting() { sshd -T -C "user=$1,host=check,addr=192.0.2.1" | awk '$1 == "passwordauthentication" { print $2 }'; }
  [[ $(setting "$admin") == no ]] \
    || { rm -f "$ssh_conf"; fail "Another SSH setting keeps passwords on for $admin (see /etc/ssh/sshd_config and sshd_config.d). Nothing was changed."; }
  for user in "${password_users[@]}"; do
    [[ $(setting "$user") == yes ]] || { rm -f "$ssh_conf"; fail "Password login for $user didn't take effect. Nothing was changed."; }
  done
fi
changed=true

# 2. Packages.
echo "Installing ufw, unattended-upgrades and fail2ban…"
apt-get update -qq
DEBIAN_FRONTEND=noninteractive apt-get install -y -qq ufw unattended-upgrades fail2ban >/dev/null

# 3. Firewall.
echo "Turning on the firewall…"
ufw default deny incoming >/dev/null
ufw default allow outgoing >/dev/null
for port in $ssh_ports; do ufw allow "$port/tcp" comment ssh >/dev/null; done
ufw allow 80/tcp comment http >/dev/null
ufw allow 443/tcp comment https >/dev/null
for port in "${extra_ports[@]}"; do ufw allow "$port/tcp" comment "kept open by harden_host.sh" >/dev/null; done
ufw --force enable >/dev/null

# 4. Automatic updates.
echo "Setting up automatic security updates…"
cat > /etc/apt/apt.conf.d/20auto-upgrades <<'EOF'
APT::Periodic::Update-Package-Lists "1";
APT::Periodic::Unattended-Upgrade "1";
EOF
cat > /etc/apt/apt.conf.d/52tapline-idp-upgrades <<EOF
Unattended-Upgrade::Automatic-Reboot "$reboot";
Unattended-Upgrade::Automatic-Reboot-Time "04:00";
Unattended-Upgrade::Remove-Unused-Dependencies "true";
EOF

# 5. Apply the SSH settings, and start fail2ban.
echo "Applying the SSH settings and starting fail2ban…"
if [[ $harden_ssh == true ]]; then systemctl reload ssh 2>/dev/null || systemctl reload sshd; fi
systemctl enable --now fail2ban >/dev/null

echo
ufw status verbose
echo
echo "Done. Before closing this session, open a NEW terminal and check you can still log in:"
for port in $ssh_ports; do echo "  ssh -p $port $admin@$(hostname -f)"; done
