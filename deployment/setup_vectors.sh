#!/usr/bin/env bash
set -euo pipefail
sudo systemctl stop neuranx-api neuranx-tunnel
sudo dnf --disablerepo='*' --enablerepo=ol9_baseos_latest --enablerepo=ol9_appstream --setopt=install_weak_deps=False install -y postgresql-server postgresql-devel gcc make git
if [ ! -d /var/lib/pgsql/data/base ]; then sudo postgresql-setup --initdb; fi
sudo systemctl enable --now postgresql
if [ ! -d /tmp/pgvector ]; then git clone --depth 1 --branch v0.8.2 https://github.com/pgvector/pgvector.git /tmp/pgvector; fi
cd /tmp/pgvector
make OPTFLAGS='' -j1
sudo make install
sudo -u postgres psql -tc "SELECT 1 FROM pg_roles WHERE rolname='opc'" | grep -q 1 || sudo -u postgres createuser opc
sudo -u postgres psql -tc "SELECT 1 FROM pg_database WHERE datname='neuranx'" | grep -q 1 || sudo -u postgres createdb -O opc neuranx
sudo -u postgres psql neuranx -c 'CREATE EXTENSION IF NOT EXISTS vector;'
sudo mkdir -p /etc/systemd/system/neuranx-api.service.d
sudo tee /etc/systemd/system/neuranx-api.service.d/vectors.conf >/dev/null <<'UNIT'
[Service]
Environment=HOSTED_VECTORS=true
Environment=OMP_NUM_THREADS=1
Environment=TOKENIZERS_PARALLELISM=false
RestartSec=5
UNIT
sudo systemctl daemon-reload
