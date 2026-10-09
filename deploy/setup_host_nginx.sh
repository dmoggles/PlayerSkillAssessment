#!/usr/bin/env bash
# Host Nginx and HTTPS for one environment on this VPS (production and development may live on different VPSes).
#
#   sudo bash setup_host_nginx.sh prod|dev DOMAIN CERT_EMAIL
#
# Run with nginx-prod.conf.example or nginx-dev.conf.example in the same directory. Production proxies to
# 127.0.0.1:8082, development to 127.0.0.1:8083.
set -euo pipefail

usage() {
  echo "Usage: sudo bash setup_host_nginx.sh prod|dev DOMAIN CERT_EMAIL" >&2
  echo "Run with nginx-prod.conf.example or nginx-dev.conf.example in the same directory." >&2
  exit 2
}

fail() { echo "Error: $*" >&2; exit 1; }

[[ $# -eq 3 && ($1 == prod || $1 == dev) ]] || usage
[[ $EUID -eq 0 ]] || fail "Run this script with sudo on the VPS."

env=$1
domain=$2
cert_email=$3
domain_pattern='^[a-z0-9]([a-z0-9-]*[a-z0-9])?(\.[a-z0-9]([a-z0-9-]*[a-z0-9])?)+$'
[[ $domain =~ $domain_pattern ]] || fail "Invalid domain: $domain"
[[ $cert_email =~ ^[^[:space:]@]+@[^[:space:]@]+\.[^[:space:]@]+$ ]] || fail "Invalid certificate email."

for command in nginx certbot systemctl getent sed install grep mktemp awk ln rm rmdir; do
  command -v "$command" >/dev/null || fail "$command is not installed."
done
systemctl is-active --quiet nginx || fail "Nginx is not running."
plugins=$(certbot plugins) || fail "Could not list Certbot plugins."
grep -qi nginx <<< "$plugins" || fail "The Certbot Nginx plugin is not installed."

script_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
template="$script_dir/nginx-$env.conf.example"
[[ -f $template ]] || fail "nginx-$env.conf.example must be alongside this script."
placeholder=$([[ $env == prod ]] && echo 'assessment\.example\.com' || echo 'dev-assessment\.example\.com')
port=$([[ $env == prod ]] && echo 8082 || echo 8083)

available=/etc/nginx/sites-available
enabled=/etc/nginx/sites-enabled
[[ -d $available && -d $enabled ]] || fail "Expected Nginx sites-available and sites-enabled directories."
site="$available/player-assessment-$env"
link="$enabled/player-assessment-$env"
for path in "$site" "$link"; do
  [[ ! -e $path && ! -L $path ]] || fail "$path already exists; inspect it before changing anything."
done

nginx -t >/dev/null || fail "Existing Nginx configuration is invalid; fix it before adding sites."
records=$(getent ahostsv4 "$domain") || fail "No IPv4 DNS result for $domain."
address=$(printf '%s\n' "$records" | awk 'NR == 1 { print $1 }')
echo "$domain resolves to $address"
if nginx -T 2>/dev/null | grep -F -q -- "$domain"; then
  fail "$domain already appears in the active Nginx configuration; inspect that site first."
fi

echo "Will add an Nginx site: $domain -> 127.0.0.1:$port."
echo "Certbot will request a certificate and redirect HTTP to HTTPS. Existing site files will not be replaced."
read -r -p "Have you verified $domain points at this VPS? Type yes to continue: " confirmation
[[ $confirmation == yes ]] || fail "Cancelled without changes."

temp_dir=$(mktemp -d)
activated=false
install_started=false
cleanup() {
  if [[ $install_started == true && $activated == false ]]; then
    rm -f -- "$link" "$site"
  fi
  rm -f -- "$temp_dir/site.conf"
  rmdir -- "$temp_dir"
}
trap cleanup EXIT

sed "s/$placeholder/$domain/g" "$template" > "$temp_dir/site.conf"
install_started=true
install -m 644 "$temp_dir/site.conf" "$site"
ln -s "$site" "$link"
nginx -t
systemctl reload nginx
activated=true

if ! certbot --nginx --non-interactive --agree-tos --email "$cert_email" --redirect -d "$domain"; then
  fail "Certificate request failed. The Nginx site remains installed; fix DNS/port 80 and rerun certbot for $domain."
fi
nginx -t
echo "Nginx and HTTPS are configured. After deploying the containers, check:"
echo "  curl --fail https://$domain/api/health"
