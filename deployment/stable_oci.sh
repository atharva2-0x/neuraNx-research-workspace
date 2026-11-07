#!/usr/bin/env bash
set -euo pipefail
sudo install -m 755 /home/opc/caddy /usr/local/bin/caddy
sudo restorecon /usr/local/bin/caddy
sudo mkdir -p /etc/caddy /var/lib/caddy
sudo tee /etc/caddy/Caddyfile >/dev/null <<'CADDY'
92-4-81-209.sslip.io {
    reverse_proxy 127.0.0.1:8000
}
CADDY
sudo tee /etc/systemd/system/caddy.service >/dev/null <<'UNIT'
[Unit]
After=network-online.target
Wants=network-online.target
[Service]
ExecStart=/usr/local/bin/caddy run --config /etc/caddy/Caddyfile
Environment=HOME=/var/lib/caddy
Restart=always
RestartSec=5
[Install]
WantedBy=multi-user.target
UNIT
sudo firewall-cmd --permanent --add-service=http
sudo firewall-cmd --permanent --add-service=https
sudo firewall-cmd --reload
sudo systemctl daemon-reload
sudo systemctl enable --now caddy
sudo systemctl disable --now dnf-makecache.timer
