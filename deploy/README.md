# Staging deployment on one Linux VPS

This package deploys one Web process behind Nginx. It is suitable for a private
staging environment and the first production deployment while SQLite remains the
primary datastore. Do not run the Telegram process in this unit; it is a separate
process with its own lifecycle.

The examples use a Debian/Ubuntu-style host, the application checkout
`/opt/intertop-training`, service user `intertop`, runtime state
`/srv/intertop-training`, and a future hostname `staging.example.com`. Replace
the hostname before running the commands. No template contains a real secret.

## 1. Prepare the host

Install a current supported Python 3, Git, Nginx and Certbot using the host's
normal package manager. Create a non-login service user and the directories that
will retain application state:

```bash
sudo useradd --system --home /nonexistent --shell /usr/sbin/nologin intertop
sudo install -d -o intertop -g intertop -m 0750 \
  /srv/intertop-training/data \
  /srv/intertop-training/courses \
  /srv/intertop-training/uploads
sudo install -d -o root -g intertop -m 0750 /etc/intertop-training
sudo install -d -o root -g root -m 0755 /var/www/certbot
```

Clone only the reviewed Git repository into `/opt/intertop-training`, create a
virtual environment, and install locked application dependencies. Never copy the
old untracked `courses/`, `docs/` or `e2e_work/` directories as part of a deploy.

```bash
sudo git clone <REPOSITORY_URL> /opt/intertop-training
sudo chown -R root:root /opt/intertop-training
cd /opt/intertop-training
sudo python3 -m venv .venv
sudo .venv/bin/pip install --upgrade pip
sudo .venv/bin/pip install -r requirements.txt
```

For an existing installation, use the approved release revision rather than a
mutable branch name, then repeat the dependency installation if requirements
changed.

## 2. Configure runtime state and secrets

Copy `staging.env.example` outside the checkout and replace the hostname and
session-secret placeholder. Generate the secret on the server; do not paste it
into chat, Git, or shell history.

```bash
cd /opt/intertop-training
sudo install -o root -g intertop -m 0640 deploy/staging.env.example \
  /etc/intertop-training/staging.env
sudoedit /etc/intertop-training/staging.env
openssl rand -base64 48
```

Set `INTERTOP_ALLOWED_HOSTS` to the exact hostname and put the generated value in
`WEB_SESSION_SECRET`. Keep `INTERTOP_WEB_HOST=127.0.0.1`; Nginx is the only
process that may receive public HTTP traffic.

Place only reviewed, published course directories in
`/srv/intertop-training/courses`. The service creates a fresh SQLite database on
first start. For an existing database, create and verify a backup before copying
it into `/srv/intertop-training/data/training.db`, then set ownership to
`intertop:intertop` and mode `0640`.

## 3. Validate data before a release

Run these commands against a backup or an offline database. They are read-only
and return non-zero when manual review is needed:

```bash
cd /opt/intertop-training
sudo -u intertop env \
  INTERTOP_DB_PATH=/srv/intertop-training/data/training.db \
  .venv/bin/python -m app.database.tenant_audit \
  --db /srv/intertop-training/data/training.db
sudo -u intertop env \
  INTERTOP_DB_PATH=/srv/intertop-training/data/training.db \
  .venv/bin/python -m app.database.platform_audit \
  --db /srv/intertop-training/data/training.db
```

Before every update, create a consistent backup outside the checkout:

```bash
cd /opt/intertop-training
sudo -u intertop .venv/bin/python -m app.database.backup \
  --db /srv/intertop-training/data/training.db \
  --output-dir /var/backups/intertop-training \
  --keep-last 14
```

Store backups on separate durable storage. A backup on the same VPS is not a
disaster-recovery backup.

## 4. Install the Web service

```bash
cd /opt/intertop-training
sudo install -o root -g root -m 0644 \
  deploy/systemd/intertop-training-web.service \
  /etc/systemd/system/intertop-training-web.service
sudo systemctl daemon-reload
sudo systemctl enable --now intertop-training-web
sudo systemctl status intertop-training-web --no-pager
curl --fail http://127.0.0.1:8000/health
curl --fail http://127.0.0.1:8000/ready
```

If either health check fails, stop here and inspect
`sudo journalctl -u intertop-training-web -n 100 --no-pager`. Do not expose Nginx
until the loopback readiness check is green.

## 5. Obtain TLS and configure Nginx

Point the future hostname's DNS record to this VPS before requesting a
certificate. First install the HTTP bootstrap template, replacing the placeholder
with the hostname:

```bash
sudo sed 's/__INTERTOP_HOSTNAME__/staging.example.com/g' \
  /opt/intertop-training/deploy/nginx/intertop-training-bootstrap-http.conf.template \
  | sudo tee /etc/nginx/sites-available/intertop-training >/dev/null
sudo ln -s /etc/nginx/sites-available/intertop-training /etc/nginx/sites-enabled/intertop-training
sudo nginx -t && sudo systemctl reload nginx
sudo certbot certonly --webroot -w /var/www/certbot -d staging.example.com
```

Then replace the bootstrap configuration with the TLS template, validate Nginx,
and reload it:

```bash
sudo sed 's/__INTERTOP_HOSTNAME__/staging.example.com/g' \
  /opt/intertop-training/deploy/nginx/intertop-training.conf.template \
  | sudo tee /etc/nginx/sites-available/intertop-training >/dev/null
sudo nginx -t && sudo systemctl reload nginx
curl --fail --location https://staging.example.com/health
curl --fail --location https://staging.example.com/ready
```

Use the provider's managed TLS equivalent when Nginx is not the public proxy;
still preserve the `Host` and `X-Forwarded-Proto` headers and set
`INTERTOP_FORWARDED_ALLOW_IPS` to the proxy's real, specific IP addresses.

## 6. Release and rollback

For every release: take a backup, run both audits, update to an approved commit,
install dependencies if required, restart the service, then run `/health` and
`/ready` through HTTPS. Complete the real platform-owner acceptance flow only
after these checks pass.

To restore, first stop the Web and Telegram processes. The restore command
creates a safety backup before replacing the database:

```bash
cd /opt/intertop-training
sudo systemctl stop intertop-training-web
sudo -u intertop .venv/bin/python -m app.database.restore \
  --backup /var/backups/intertop-training/training-backup-TIMESTAMP.sqlite3 \
  --db /srv/intertop-training/data/training.db \
  --safety-backup-dir /var/backups/intertop-training/pre-restore
sudo systemctl start intertop-training-web
```

Run `/ready` after the restart and keep the safety backup until the smoke test is
complete.
