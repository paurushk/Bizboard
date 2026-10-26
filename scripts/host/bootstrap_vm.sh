#!/usr/bin/env bash
# WP-4 (BB-080/085): prepare a fresh Ubuntu LTS VM to run the Bizboard compose stack.
# Provider-neutral. Safe to re-run. `--check` changes nothing and reports what is missing.
#
#   sudo scripts/host/bootstrap_vm.sh --deploy-user bizboard --ssh-key "ssh-ed25519 AAAA... you@laptop"
#   sudo scripts/host/bootstrap_vm.sh --check
#
# What it does:
#   1. deploy user with SSH key login only (password and root SSH login off)
#   2. ufw: allow 22 and 443 (and 80 for the HTTPS redirect) unless --tunnel (Cloudflare tunnel:
#      nothing public but 22)
#   3. unattended security upgrades, time sync, a swap file, journald size cap
#   4. Docker Engine + compose plugin from Docker's apt repository; deploy user in the docker group
#
# Docker bypasses ufw: a container port published on 0.0.0.0 is reachable whatever ufw says.
# The stack therefore binds published ports to loopback (APP_BIND=127.0.0.1 in docker-compose.yml,
# GlitchTip on 127.0.0.1). Keep it that way; scripts/host/preflight.py checks it on the host.
# This script does not edit Docker's iptables chains.
set -euo pipefail

CHECK=0; TUNNEL=0; DEPLOY_USER="bizboard"; SSH_KEY=""; SWAP_GB=2
while [[ $# -gt 0 ]]; do
  case "$1" in
    --check) CHECK=1 ;;
    --tunnel) TUNNEL=1 ;;
    --deploy-user) DEPLOY_USER="$2"; shift ;;
    --ssh-key) SSH_KEY="$2"; shift ;;
    --swap-gb) SWAP_GB="$2"; shift ;;
    *) echo "unknown option $1" >&2; exit 2 ;;
  esac
  shift
done

missing=0
report() { printf '%-6s %s\n' "$1" "$2"; [[ "$1" == "MISS" ]] && missing=$((missing + 1)); return 0; }
have() { command -v "$1" >/dev/null 2>&1; }

. /etc/os-release 2>/dev/null || true
[[ "${ID:-}" == "ubuntu" ]] || report WARN "not Ubuntu (${ID:-unknown}); steps assume Ubuntu LTS"

# --- checks (always) ---------------------------------------------------------------------------
id "$DEPLOY_USER" >/dev/null 2>&1 && report ok "deploy user $DEPLOY_USER" || report MISS "deploy user $DEPLOY_USER"
grep -Eqs '^\s*PasswordAuthentication\s+no' /etc/ssh/sshd_config /etc/ssh/sshd_config.d/*.conf \
  && report ok "SSH password login off" || report MISS "SSH password login off"
grep -Eqs '^\s*PermitRootLogin\s+(no|prohibit-password)' /etc/ssh/sshd_config /etc/ssh/sshd_config.d/*.conf \
  && report ok "SSH root login off" || report MISS "SSH root login off"
if have ufw && ufw status 2>/dev/null | grep -q "Status: active"; then report ok "ufw active"; else report MISS "ufw active"; fi
dpkg -s unattended-upgrades >/dev/null 2>&1 && report ok "unattended-upgrades" || report MISS "unattended-upgrades"
timedatectl show -p NTPSynchronized --value 2>/dev/null | grep -q yes && report ok "time synced" || report MISS "time synced"
swapon --show 2>/dev/null | grep -q . && report ok "swap" || report MISS "swap"
grep -qs '^SystemMaxUse=' /etc/systemd/journald.conf.d/bizboard.conf && report ok "journald cap" || report MISS "journald cap"
if have docker && docker compose version >/dev/null 2>&1; then report ok "docker + compose"; else report MISS "docker + compose"; fi
id -nG "$DEPLOY_USER" 2>/dev/null | grep -qw docker && report ok "$DEPLOY_USER in docker group" || report MISS "$DEPLOY_USER in docker group"

if [[ $CHECK -eq 1 ]]; then
  echo "missing: $missing"
  exit $(( missing > 0 ? 1 : 0 ))
fi
[[ $EUID -eq 0 ]] || { echo "run as root (sudo)" >&2; exit 1; }
[[ $missing -eq 0 ]] && { echo "nothing to do"; exit 0; }

# --- apply --------------------------------------------------------------------------------------
export DEBIAN_FRONTEND=noninteractive
apt-get update -y
apt-get install -y ca-certificates curl gnupg ufw unattended-upgrades chrony

if ! id "$DEPLOY_USER" >/dev/null 2>&1; then
  adduser --disabled-password --gecos "" "$DEPLOY_USER"
fi
if [[ -n "$SSH_KEY" ]]; then
  install -d -m 700 -o "$DEPLOY_USER" -g "$DEPLOY_USER" "/home/$DEPLOY_USER/.ssh"
  touch "/home/$DEPLOY_USER/.ssh/authorized_keys"
  grep -qxF "$SSH_KEY" "/home/$DEPLOY_USER/.ssh/authorized_keys" || echo "$SSH_KEY" >> "/home/$DEPLOY_USER/.ssh/authorized_keys"
  chown "$DEPLOY_USER:$DEPLOY_USER" "/home/$DEPLOY_USER/.ssh/authorized_keys"; chmod 600 "/home/$DEPLOY_USER/.ssh/authorized_keys"
fi
if [[ -s "/home/$DEPLOY_USER/.ssh/authorized_keys" ]]; then
  # Only lock password login once a key is in place, so the operator is not locked out.
  printf 'PasswordAuthentication no\nPermitRootLogin prohibit-password\nKbdInteractiveAuthentication no\n' \
    > /etc/ssh/sshd_config.d/50-bizboard.conf
  systemctl reload ssh || systemctl reload sshd || true
else
  echo "WARN: no SSH key for $DEPLOY_USER; password login left on. Re-run with --ssh-key." >&2
fi

ufw default deny incoming
ufw default allow outgoing
ufw allow 22/tcp
if [[ $TUNNEL -eq 0 ]]; then ufw allow 80/tcp; ufw allow 443/tcp; fi
ufw --force enable

dpkg-reconfigure -f noninteractive unattended-upgrades
systemctl enable --now chrony

if ! swapon --show | grep -q .; then
  fallocate -l "${SWAP_GB}G" /swapfile && chmod 600 /swapfile && mkswap /swapfile && swapon /swapfile
  grep -q '^/swapfile ' /etc/fstab || echo '/swapfile none swap sw 0 0' >> /etc/fstab
fi
install -d /etc/systemd/journald.conf.d
printf '[Journal]\nSystemMaxUse=1G\n' > /etc/systemd/journald.conf.d/bizboard.conf
systemctl restart systemd-journald

if ! docker compose version >/dev/null 2>&1; then
  install -m 0755 -d /etc/apt/keyrings
  curl -fsSL "https://download.docker.com/linux/ubuntu/gpg" -o /etc/apt/keyrings/docker.asc
  chmod a+r /etc/apt/keyrings/docker.asc
  echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu ${VERSION_CODENAME} stable" \
    > /etc/apt/sources.list.d/docker.list
  apt-get update -y
  apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
fi
# Container logs: cap size so a chatty container cannot fill the disk.
if [[ ! -f /etc/docker/daemon.json ]]; then
  printf '{\n  "log-driver": "json-file",\n  "log-opts": {"max-size": "20m", "max-file": "5"}\n}\n' > /etc/docker/daemon.json
  systemctl restart docker
fi
usermod -aG docker "$DEPLOY_USER"

echo "done. Next: clone the repo as $DEPLOY_USER into STAGING_DIR, render .env (scripts/host/render_env.sh),"
echo "deploy, then run scripts/host/preflight.py on this host."
