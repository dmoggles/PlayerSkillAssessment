#!/usr/bin/env bash
set -euo pipefail

usage() {
  echo "Usage: sudo bash setup_host_nginx.sh PROD_DOMAIN DEV_DOMAIN CERT_EMAIL" >&2
  echo "Run with nginx-prod.conf.example and nginx-dev.conf.example in the same directory." >&2
  exit 2
}

fail() { echo "Error: $*" >&2; exit 1; }

[[ $# -eq 3 ]] || usage
[[ $EUID -eq 0 ]] || fail "Run this script with sudo on the VPS."

prod_domain=$1
dev_domain=$2
cert_email=$3
domain_pattern='^[a-z0-9]([a-z0-9-]*[a-z0-9])?(\.[a-z0-9]([a-z0-9-]*[a-z0-9])?)+$'
[[ $prod_domain =~ $domain_pattern ]] || fail "Invalid production domain: $prod_domain"
[[ $dev_domain =~ $domain_pattern ]] || fail "Invalid development domain: $dev_domain"
[[ $prod_domain != "$dev_domain" ]] || fail "Production and development need different domains."
[[ $cert_email =~ ^[^[:space:]@]+@[^[:space:]@]+\.[^[:space:]@]+$ ]] || fail "Invalid certificate email."

for command in nginx certbot systemctl getent sed install grep mktemp awk ln rm rmdir; do
  command -v "$command" >/dev/null || fail "$command is not installed."
done
systemctl is-active --quiet nginx || fail "Nginx is not running."
plugins=$(certbot plugins) || fail "Could not list Certbot plugins."
grep -qi nginx <<< "$plugins" || fail "The Certbot Nginx plugin is not installed."

script_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
prod_template="$script_dir/nginx-prod.conf.example"
dev_template="$script_dir/nginx-dev.conf.example"
[[ -f $prod_template && -f $dev_template ]] || fail "Both Nginx templates must be alongside this script."

available=/etc/nginx/sites-available
enabled=/etc/nginx/sites-enabled
[[ -d $available && -d $enabled ]] || fail "Expected Nginx sites-available and sites-enabled directories."
prod_site="$available/player-assessment-prod"
dev_site="$available/player-assessment-dev"
prod_link="$enabled/player-assessment-prod"
dev_link="$enabled/player-assessment-dev"
for path in "$prod_site" "$dev_site" "$prod_link" "$dev_link"; do
  [[ ! -e $path && ! -L $path ]] || fail "$path already exists; inspect it before changing anything."
done

nginx -t >/dev/null || fail "Existing Nginx configuration is invalid; fix it before adding sites."
existing_config=$(nginx -T 2>/dev/null)
for domain in "$prod_domain" "$dev_domain"; do
  records=$(getent ahostsv4 "$domain") || fail "No IPv4 DNS result for $domain."
  address=$(printf '%s\n' "$records" | awk 'NR == 1 { print $1 }')
  echo "$domain resolves to $address"
  if grep -F -q -- "$domain" <<< "$existing_config"; then
    fail "$domain already appears in the active Nginx configuration; inspect that site first."
  fi
done

echo "Will add two Nginx sites: $prod_domain -> 127.0.0.1:8082 and $dev_domain -> 127.0.0.1:8083."
echo "Certbot will request certificates and redirect HTTP to HTTPS. Existing site files will not be replaced."
read -r -p "Have you verified both DNS addresses are this VPS? Type yes to continue: " confirmation
[[ $confirmation == yes ]] || fail "Cancelled without changes."

temp_dir=$(mktemp -d)
activated=false
install_started=false
cleanup() {
  if [[ $install_started == true && $activated == false ]]; then
    rm -f -- "$prod_link" "$dev_link" "$prod_site" "$dev_site"
  fi
  rm -f -- "$temp_dir/prod.conf" "$temp_dir/dev.conf"
  rmdir -- "$temp_dir"
}
trap cleanup EXIT

sed "s/assessment\.example\.com/$prod_domain/g" "$prod_template" > "$temp_dir/prod.conf"
sed "s/dev-assessment\.example\.com/$dev_domain/g" "$dev_template" > "$temp_dir/dev.conf"
install_started=true
install -m 644 "$temp_dir/prod.conf" "$prod_site"
install -m 644 "$temp_dir/dev.conf" "$dev_site"
ln -s "$prod_site" "$prod_link"
ln -s "$dev_site" "$dev_link"
nginx -t
systemctl reload nginx
activated=true

if ! certbot --nginx --non-interactive --agree-tos --email "$cert_email" --redirect -d "$prod_domain"; then
  fail "Production certificate failed. Nginx sites remain installed; fix DNS/port 80 and rerun certbot for $prod_domain."
fi
if ! certbot --nginx --non-interactive --agree-tos --email "$cert_email" --redirect -d "$dev_domain"; then
  fail "Development certificate failed. Nginx sites remain installed; fix DNS/port 80 and rerun certbot for $dev_domain."
fi
nginx -t
echo "Nginx and HTTPS are configured. After deploying the containers, check:"
echo "  curl --fail https://$prod_domain/api/health"
echo "  curl --fail https://$dev_domain/api/health"
