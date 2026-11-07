#!/usr/bin/env bash
set -euo pipefail
# Place service executables outside the home directory; retain SELinux enforcement.
sudo mkdir -p /opt/neuranx
sudo cp -a /home/opc/fund-api/. /opt/neuranx/
sudo chown -R opc:opc /opt/neuranx
sudo install -m 755 /home/opc/cloudflared /usr/local/bin/cloudflared
sudo restorecon /usr/local/bin/cloudflared
sudo restorecon -R /opt/neuranx
sudo sed -i 's@WorkingDirectory=/home/opc/fund-api@WorkingDirectory=/opt/neuranx@;s@ExecStart=/home/opc/fund-api/.venv/bin/uvicorn@Environment=PYTHONPATH=/opt/neuranx/.venv/lib/python3.9/site-packages\nExecStart=/usr/bin/python3 -m uvicorn@' /etc/systemd/system/neuranx-api.service
sudo sed -i 's@ExecStart=/home/opc/cloudflared@ExecStart=/usr/local/bin/cloudflared@' /etc/systemd/system/neuranx-tunnel.service
python3 - <<'PY'
from pathlib import Path
p=Path('/opt/neuranx/api/index.py')
s=p.read_text().replace("'read-only Vercel demo'","'OCI read-only demo'").replace("'oci_connected':False","'oci_connected':True")
p.write_text(s)
PY
sudo systemctl daemon-reload
sudo systemctl reset-failed neuranx-api neuranx-tunnel
sudo systemctl restart neuranx-api neuranx-tunnel
curl --fail --retry 8 --retry-connrefused --retry-delay 2 http://127.0.0.1:8000/health
sudo journalctl -u neuranx-tunnel --no-pager -n 25
