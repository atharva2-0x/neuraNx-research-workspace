#!/usr/bin/env bash
set -euo pipefail
if ! sudo swapon --show | grep -q /swap-neuranx; then
  sudo fallocate -l 1G /swap-neuranx
  sudo chmod 600 /swap-neuranx
  sudo mkswap /swap-neuranx
  sudo swapon /swap-neuranx
fi
mkdir -p /home/opc/fund-api
tar -xzf /home/opc/oci-app.tar.gz -C /home/opc/fund-api
cd /home/opc/fund-api
python3 -m venv .venv
.venv/bin/pip install fastapi==0.115.6 pydantic==2.10.6 httpx==0.28.1 uvicorn==0.34.0
curl --fail --location --retry 3 -o /home/opc/cloudflared https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64
chmod 755 /home/opc/cloudflared
sudo tee /etc/systemd/system/neuranx-api.service >/dev/null <<'SERVICE'
[Unit]
Description=NeuraNx sample evidence API
After=network-online.target
[Service]
User=opc
WorkingDirectory=/home/opc/fund-api
ExecStart=/home/opc/fund-api/.venv/bin/uvicorn api.index:app --host 127.0.0.1 --port 8000
Restart=on-failure
NoNewPrivileges=true
PrivateTmp=true
[Install]
WantedBy=multi-user.target
SERVICE
sudo tee /etc/systemd/system/neuranx-tunnel.service >/dev/null <<'SERVICE'
[Unit]
Description=NeuraNx demonstration HTTPS tunnel
After=network-online.target neuranx-api.service
[Service]
User=opc
ExecStart=/home/opc/cloudflared tunnel --no-autoupdate --protocol http2 --url http://127.0.0.1:8000
Restart=on-failure
NoNewPrivileges=true
PrivateTmp=true
[Install]
WantedBy=multi-user.target
SERVICE
sudo systemctl daemon-reload
sudo systemctl enable --now neuranx-api neuranx-tunnel
curl --fail --retry 5 --retry-connrefused --retry-delay 2 http://127.0.0.1:8000/health
sudo journalctl -u neuranx-tunnel --no-pager -n 30
