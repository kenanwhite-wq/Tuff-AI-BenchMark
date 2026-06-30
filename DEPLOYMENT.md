# Deploying Tuff AI Benchmark on Ubuntu (Vultr VPS)

This guide deploys the app to a Vultr VPS running Ubuntu with **tuffai.net**, using the **xAI API** for LLM tasks. Ollama is **not** required in production.

## Architecture

```mermaid
flowchart TB
    user[Browser] --> nginx[Nginx :443]
    nginx --> static[React build /opt/tuffai/frontend/build]
    nginx --> api[Flask API via Gunicorn :5001]
    scheduler[Timer.py systemd service] --> fetcher[hourlyfetcher.py]
    scheduler --> scanner[news_scanner.py]
    fetcher --> sqlite[(benchmark.db)]
    scanner --> sqlite
    api --> sqlite
    fetcher --> xai[xAI API]
    scanner --> xai
    api --> xai
    fetcher --> aa[Artificial Analysis API]
```

| Component | Role |
|-----------|------|
| Nginx | HTTPS, static React files, reverse proxy for `/api/` |
| Gunicorn | Production Flask API on `127.0.0.1:5001` |
| Timer.py | Hourly benchmark fetch + news scan |
| xAI API | Model normalization, news classification, article summaries |
| SQLite | `benchmark.db` on disk |

## VPS sizing

Without Ollama, a smaller instance is sufficient:

| Resource | Minimum |
|----------|---------|
| RAM | 4 GB (8 GB recommended) |
| vCPUs | 2 |
| Disk | 20 GB |

## Prerequisites

On a fresh Ubuntu 22.04/24.04 VPS:

- Python 3.9+
- Node.js 18+
- Nginx
- Certbot
- Git

Do **not** install Ollama on the production server.

## 1. Initial server setup

```bash
ssh root@YOUR_VPS_IP

apt update && apt upgrade -y
apt install -y python3 python3-venv python3-pip nginx git curl ufw

# Node.js 20
curl -fsSL https://deb.nodesource.com/setup_20.x | bash -
apt install -y nodejs

# Deploy user
adduser deploy
usermod -aG sudo deploy

ufw allow OpenSSH
ufw allow 80
ufw allow 443
ufw enable
```

Copy your SSH key to the `deploy` user, then continue as that user.

## 2. Clone the application

```bash
sudo mkdir -p /opt/tuffai
sudo chown deploy:deploy /opt/tuffai

cd /opt/tuffai
git clone https://github.com/kenanwhite-wq/Tuff-AI-BenchMark.git .
```

## 3. Environment variables

```bash
cp .env.example .env
nano .env
```

Production `.env` example:

```env
ARTIFICIAL_ANALYSIS_API_KEY=your_key_from_artificialanalysis.ai
ADMIN_TOKEN=your_random_secret

LLM_PROVIDER=xai
XAI_API_KEY=your_key_from_console.x.ai
XAI_MODEL=grok-4.20-0309-non-reasoning
XAI_API_BASE=https://api.x.ai/v1
```

Generate `ADMIN_TOKEN`:

```bash
python3 -c 'import secrets; print(secrets.token_hex(32))'
```

Get API keys:

- Artificial Analysis: https://artificialanalysis.ai (free tier available)
- xAI: https://console.x.ai/team/default/api-keys

## 4. Python backend

```bash
cd /opt/tuffai
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pip install gunicorn
```

Validate LLM configuration and seed the database (first run may take several minutes and incur xAI API costs for uncached model names):

```bash
python3 hourlyfetcher.py
```

## 5. Build the frontend

```bash
cd /opt/tuffai/frontend
npm install
REACT_APP_API_BASE_URL=/api npm run build
```

## 6. systemd services

Copy the unit files from this repo:

```bash
sudo cp /opt/tuffai/deploy/systemd/tuffai-api.service /etc/systemd/system/
sudo cp /opt/tuffai/deploy/systemd/tuffai-scheduler.service /etc/systemd/system/
```

Enable and start:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now tuffai-api tuffai-scheduler
sudo systemctl status tuffai-api tuffai-scheduler
```

View logs:

```bash
sudo journalctl -u tuffai-api -f
sudo journalctl -u tuffai-scheduler -f
tail -f /opt/tuffai/fetcher.log
```

## 7. Nginx

```bash
# Disable Ubuntu's default site (avoids conflicting server_name warnings)
sudo rm -f /etc/nginx/sites-enabled/default

sudo cp /opt/tuffai/deploy/nginx/tuffai.net.conf /etc/nginx/sites-available/tuffai.net
sudo ln -sf /etc/nginx/sites-available/tuffai.net /etc/nginx/sites-enabled/tuffai.net
sudo nginx -t
sudo systemctl reload nginx
```

Confirm only one enabled site references `tuffai.net`:

```bash
grep -r "server_name" /etc/nginx/sites-enabled/
```

Flask listens on `127.0.0.1:5001` only — do not expose it publicly.

## 8. DNS (tuffai.net)

At your DNS provider, create:

| Type | Name | Value |
|------|------|-------|
| A | `@` | `YOUR_VPS_IP` |
| A | `www` | `YOUR_VPS_IP` |

Wait for DNS propagation before requesting TLS certificates.

## 9. HTTPS with Let's Encrypt

**Important:** Complete sections 7 (Nginx site config for `tuffai.net`) and 8 (DNS) before running Certbot. If Certbot runs while only the Ubuntu `default` site is enabled, it will attach the certificate to the wrong config and you will see `conflicting server name` warnings and renewal failures.

Create the ACME challenge directory and ensure nginx can serve it (the deploy config includes this block):

```bash
sudo mkdir -p /var/www/certbot
sudo chown -R www-data:www-data /var/www/certbot
```

Update nginx if you deployed before this block existed — add inside the `server { ... }` for port 80, **before** `location /`:

```nginx
location ^~ /.well-known/acme-challenge/ {
    root /var/www/certbot;
    allow all;
}
```

Then:

```bash
sudo nginx -t
sudo systemctl reload nginx
sudo apt install -y certbot python3-certbot-nginx
sudo certbot --nginx -d tuffai.net -d www.tuffai.net
```

Choose to redirect HTTP to HTTPS when prompted.

Certbot configures auto-renewal. Test renewal with:

```bash
sudo certbot renew --dry-run
```

## 10. Verification checklist

```bash
# API reachable through Nginx
curl -I https://tuffai.net
curl https://tuffai.net/api/composite

# Services running
sudo systemctl is-active tuffai-api tuffai-scheduler nginx

# Scheduler produced data
ls -lh /opt/tuffai/benchmark.db
tail -n 50 /opt/tuffai/fetcher.log
```

In a browser:

1. Open `https://tuffai.net`
2. Confirm leaderboard data loads
3. Open a news article and confirm the AI summary generates

## Operations

### Backups

Back up the SQLite database regularly:

```bash
cp /opt/tuffai/benchmark.db /opt/tuffai/backups/benchmark-$(date +%F).db
```

### Redeploy after code changes

```bash
cd /opt/tuffai
git pull
source .venv/bin/activate
pip install -r requirements.txt

cd frontend
npm install
REACT_APP_API_BASE_URL=/api npm run build

sudo systemctl restart tuffai-api tuffai-scheduler
```

### Log locations

| File | Contents |
|------|----------|
| `fetcher.log` | Hourly benchmark fetch output |
| `logs/flask.log` | Dev-only; production uses journalctl |
| `journalctl -u tuffai-api` | Gunicorn / Flask errors |
| `journalctl -u tuffai-scheduler` | Scheduler errors |

### Cost notes

xAI usage is highest on the first `hourlyfetcher.py` run, when many model names are normalized and cached in SQLite. After that, costs are mostly driven by hourly news classification and on-demand article summaries.

## Local development vs production

| Setting | Local dev | Production VPS |
|---------|-----------|----------------|
| `LLM_PROVIDER` | `ollama` (default) | `xai` |
| Ollama | Required (`ollama pull qwen3:8b`) | Not installed |
| Frontend | `npm start` on port 3000 | `npm run build` served by Nginx |
| Backend | `python SimpleWeb.py` or `./start.sh` | Gunicorn via systemd |
| `start.sh` | Dev helper only (hardcoded path) | Do not use |

For local development, see [README.md](README.md).

## Troubleshooting

**Scheduler exits immediately**

- Check `.env` has `LLM_PROVIDER=xai` and `XAI_API_KEY` set
- Run `python3 -c "from llm_client import validate_llm_config; validate_llm_config()"`

**Empty leaderboard**

- Run `python3 hourlyfetcher.py` manually and inspect output
- Confirm `ARTIFICIAL_ANALYSIS_API_KEY` is valid

**`conflicting server name "tuffai.net" ... ignored`**

Nginx found two configs claiming `tuffai.net` on port 80. The duplicate is ignored, so visitors may see the wrong site (often the Ubuntu default page).

```bash
# See what is enabled
ls -la /etc/nginx/sites-enabled/

# Find all tuffai.net definitions
grep -r "server_name" /etc/nginx/sites-available/ /etc/nginx/sites-enabled/

# Remove the default site and duplicate symlinks
sudo rm -f /etc/nginx/sites-enabled/default
sudo rm -f /etc/nginx/sites-enabled/tuffai.net  # remove broken/duplicate symlink if needed
sudo ln -sf /etc/nginx/sites-available/tuffai.net /etc/nginx/sites-enabled/tuffai.net

# If certbot created a separate file, keep only one — e.g.:
# sudo rm -f /etc/nginx/sites-enabled/tuffai.net-le-ssl
# and merge SSL into sites-available/tuffai.net, OR keep the certbot file and remove the plain one

sudo nginx -t
sudo systemctl reload nginx
```

Also confirm the React build exists:

```bash
ls -la /opt/tuffai/frontend/build/index.html
```

**Certbot cert landed on `default` instead of `tuffai.net`**

This happens when Certbot was run before the `tuffai.net` nginx site was enabled.

```bash
# See where SSL was configured
grep -r "ssl_certificate" /etc/nginx/sites-available/ /etc/nginx/sites-enabled/
ls -la /etc/nginx/sites-enabled/

# 1. Ensure tuffai.net site is correct (HTTP + app proxy + acme-challenge)
sudo nano /etc/nginx/sites-available/tuffai.net

# 2. Disable default entirely
sudo rm -f /etc/nginx/sites-enabled/default

# 3. Re-run certbot so it updates the tuffai.net config
sudo certbot --nginx -d tuffai.net -d www.tuffai.net

# 4. Confirm only tuffai.net is enabled and has ssl_certificate lines
grep -r "server_name\|ssl_certificate" /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl reload nginx
```

If Certbot refuses to re-install, delete and start fresh:

```bash
sudo certbot delete --cert-name tuffai.net
sudo certbot --nginx -d tuffai.net -d www.tuffai.net
```

**Certbot / renewal fails (`orderNotReady`, `invalid`)**

Usually means Let's Encrypt could not verify domain ownership over HTTP. Common causes: missing ACME challenge path, DNS not pointing at the VPS, or a broken partial cert from a previous attempt.

```bash
# 1. Confirm DNS
dig tuffai.net +short
dig www.tuffai.net +short
# Both must return your VPS public IP

# 2. Confirm port 80 reaches nginx
curl -I http://tuffai.net

# 3. Ensure ACME directory exists
sudo mkdir -p /var/www/certbot
echo test | sudo tee /var/www/certbot/test.txt
curl http://tuffai.net/.well-known/acme-challenge/test.txt
# Must return "test", not index.html

# 4. Inspect existing cert state
sudo certbot certificates
sudo tail -50 /var/log/letsencrypt/letsencrypt.log

# 5. Delete broken cert and re-issue cleanly
sudo certbot delete --cert-name tuffai.net
sudo certbot --nginx -d tuffai.net -d www.tuffai.net

# 6. Re-test renewal
sudo certbot renew --dry-run
```

If using **Cloudflare** (orange cloud / proxied DNS), either:
- Set DNS to **DNS only** (grey cloud) while running certbot, then re-enable proxy with SSL mode **Full (strict)**, or
- Use a [Cloudflare Origin Certificate](https://developers.cloudflare.com/ssl/origin-configuration/origin-ca/) on the VPS instead of Let's Encrypt.

**502 Bad Gateway from Nginx**

- `sudo systemctl status tuffai-api`
- Confirm Gunicorn is listening: `ss -tlnp | grep 5001`

**`ModuleNotFoundError: No module named 'SimpleWeb'`**

- The Flask app must be named `SimpleWeb.py` (with `.py` extension) so Gunicorn can import `wsgi:app`
- After pulling the fix: `git pull && sudo systemctl restart tuffai-api`

**Article summaries fail**

- Check xAI API key and account credits
- `sudo journalctl -u tuffai-api -n 100`