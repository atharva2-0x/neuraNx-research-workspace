# Cloud interview deployment

The public application is at https://neuranx-fund-intelligence.vercel.app/ and the shareable HTML deck is at `/deck.html` after the final package deployment. The same deck is saved under `output/Fund_Intelligence_FDE_Deck.html` as one self-contained file, with the live product screenshot embedded.

## Running services

- Vercel project: `neuranx-fund-intelligence` in the existing Hobby team.
- OCI instance: `neuranx-fund-api`, Mumbai (`ap-mumbai-1`), `VM.Standard.E2.1.Micro`, Oracle Linux 9, 1 GB RAM, default 46.6 GB boot volume.
- Public address at creation: `92.4.81.209`; SSH user: `opc`.
- `neuranx-api.service`: API listening on `127.0.0.1:8000`, application at `/opt/neuranx`.
- `neuranx-tunnel.service`: the explicitly approved Cloudflare HTTPS demo tunnel. Its configured origin is recorded in `deployment/backend.json`.
- Vercel serves the custom UI and source-page images from its CDN. Its Python function proxies document and question requests to OCI. Successful proxied responses include `X-Backend: OCI`.

The ARM allowance was already exceeded by existing resources. The new micro shape was labeled Always Free-eligible. Before creation the console showed 200 GB of free volume allowance, 100 GB used, and 100 GB available. The default boot disk fits in that remaining allowance. No account upgrade or paid resource was selected. Usage and eligibility must still be monitored in the OCI console.

## Public demo boundary

The fictional ABC Company Fund sample is shared. Hosted uploads (PDFs up to 4 MB and 200 pages) use isolated browser workspaces backed by an HttpOnly, Secure cookie. Each workspace can hold 10 reports; clearing cookies loses access to that workspace. Original PDFs and extracted evidence persist on the OCI disk. The deployed API reads verified evidence retained on the VM disk; it does not claim that a serverless filesystem is a durable database.

The OCI sample API uses an isolated environment compatible with the system Python runtime. Its small dependency set is pinned in the setup script. The complete local application continues to use the project's Python environment and full dependencies.

## HTTPS tunnel limitation

A Cloudflare Quick Tunnel is intended for demos, has no uptime guarantee, and assigns a new hostname if its process restarts. Both services start at boot, but Vercel's origin must be updated if the tunnel address changes. For a durable customer deployment, use a fixed hostname with TLS or a named authenticated tunnel, plus application authentication and document authorization.

To inspect the services, connect using the project key retained in `deployment/.secrets/neuranx-oci` (excluded from version control and deployment packages):

```sh
ssh -i deployment/.secrets/neuranx-oci opc@92.4.81.209
sudo systemctl status neuranx-api neuranx-tunnel
sudo journalctl -u neuranx-api -n 50
sudo journalctl -u neuranx-tunnel -n 50
curl http://127.0.0.1:8000/health
```

Do not share the private key or include it in the interview deck. Oracle Linux security enforcement remains enabled. Service binaries were placed under standard service directories rather than disabling protection to execute them from a home directory.

## Updating the deployment

`python -m scripts.prepare_vercel` creates a strictly scoped package under `deploy/vercel` and `output/fund-intelligence-vercel.zip`. Upload that ZIP through Vercel Drop, choose **Deploy to an existing project**, and select `neuranx-fund-intelligence`. The package contains the fictional sample evidence, UI, source images, read-only API/proxy, and HTML deck; it excludes credentials and local databases.

If the tunnel changes, update `deployment/backend.json`, rebuild the package, and deploy it to the same project. Verify `/health` reports `oci_connected: true` and check a cited question after every deployment.
