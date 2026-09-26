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
sudo install -d -o intertop -g intertop -m 0750 /var/backups/intertop-training
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
.venv/bin/python -c \
  'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())'
```

Set `INTERTOP_ALLOWED_HOSTS` to the exact hostname and put the generated value in
`WEB_SESSION_SECRET`. Put the Fernet value in `INTERTOP_MFA_ENCRYPTION_KEY`.
Store both values in the approved password manager as well as on the server.
The MFA encryption key is required to decrypt enrolled company-administrator
authenticator secrets and must not be rotated without resetting and re-enrolling
every administrator. Keep `INTERTOP_WEB_HOST=127.0.0.1`; Nginx is the only
process that may receive public HTTP traffic.

Place only reviewed, published course directories in
`/srv/intertop-training/courses`. The service creates a fresh SQLite database on
first start. For an existing database, create and verify a backup before copying
it into `/srv/intertop-training/data/training.db`, then set ownership to
`intertop:intertop` and mode `0640`.

## 3. Bootstrap the first platform owner

For a new Web-only installation, run this command exactly once before enabling
the Web service. The command initializes the database when needed, then prompts
on the VPS for the owner email and password; the password is not echoed or
placed in shell history. It atomically creates the user, Argon2 password
credential, sole platform-owner role, and audit event. It refuses to run when
any platform administrator already exists.

```bash
cd /opt/intertop-training
sudo -u intertop .venv/bin/python -m app.platform_owner_setup \
  --db /srv/intertop-training/data/training.db
```

Use `/platform-admin/login` through HTTPS to sign in. Create tenant companies
and their administrators only from the platform-owner interface.

### Enable two-step protection for the owner

Generate a Base32 setup key on the VPS. Add that key manually to Google
Authenticator, Microsoft Authenticator, 1Password, or another TOTP application.
Do not paste the key into chat or commit it to Git.

```bash
cd /opt/intertop-training
sudo -u intertop .venv/bin/python -m app.platform_owner_mfa_setup
sudoedit /etc/intertop-training/staging.env
```

Add the displayed key to the protected environment file:

```text
INTERTOP_PLATFORM_OWNER_TOTP_SECRET=THE_DISPLAYED_SETUP_KEY
```

Restart the Web service and confirm that the owner login rejects a missing code
and accepts the current six-digit code from the authenticator application:

```bash
sudo systemctl restart intertop-training-web
```

### Tenant administrator MFA

MFA is mandatory for every active company membership with role `admin`. On the
first successful password login the application shows a one-time setup key and
does not issue a tenant session until the current six-digit code is confirmed.
Later logins require password plus a fresh code; an accepted code cannot be
replayed in the same time window. The TOTP secret is encrypted in SQLite with
`INTERTOP_MFA_ENCRYPTION_KEY`.

If an administrator loses the authenticator, the platform owner can open
`/platform-admin/companies`, enter a reason and freshly confirm the owner
password to reset MFA. The target administrator is resolved through the selected
company, and the reset is written to the immutable platform audit log. MFA is
attached to the user account: if the same account administers several companies,
one reset affects that account everywhere. The administrator must enroll again
on the next login.

## 4. Validate data before a release

Run the combined preflight against a backup or an offline database after the
database has been initialized and its platform owner bootstrapped. It checks the
remote environment, external runtime paths, loopback Web listener and both tenant
and platform database audits. It is read-only and returns non-zero when manual
review is needed:

```bash
cd /opt/intertop-training
sudo -u intertop /opt/intertop-training/.venv/bin/python -m app.database.migrate
sudo -u intertop /opt/intertop-training/.venv/bin/python -m app.deployment_audit
```

For a detailed diagnostic of one audit category, use these read-only commands:

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

The checked-in Web unit first applies idempotent schema migrations and then runs
the combined deployment audit through `ExecStartPre`. Always create the release
backup before restarting. A failed migration or non-clean tenant/platform audit
blocks the Web process instead of serving a release over inconsistent data.

### Enable the daily integrity audit

Install and enable the audit timer. It runs the same combined audit every day
after the normal backup window. A failed audit makes the oneshot unit fail and
records the exact findings in the system journal.

```bash
cd /opt/intertop-training
sudo install -o root -g root -m 0644 \
  deploy/systemd/intertop-training-audit.service \
  /etc/systemd/system/intertop-training-audit.service
sudo install -o root -g root -m 0644 \
  deploy/systemd/intertop-training-audit.timer \
  /etc/systemd/system/intertop-training-audit.timer
sudo systemctl daemon-reload
sudo systemctl enable --now intertop-training-audit.timer
sudo systemctl start intertop-training-audit.service
sudo systemctl status intertop-training-audit.service --no-pager -l
sudo systemctl list-timers intertop-training-audit.timer --no-pager
```

Connect systemd failure notifications to the organisation's monitoring channel
before relying on this as unattended alerting. Until then, inspect failed units
and the journal as part of the daily operational checklist.

## 4. Enable verified daily backups

The timer starts a consistent SQLite backup once each day at 03:15 server time,
with a random delay of up to 30 minutes. It keeps the newest 14 local snapshots.
This is a recovery layer, not an offsite backup strategy: replicate the resulting
files to separate durable storage using the organisation's approved backup tool.
The SQLite backup connection uses `mode=ro`, but SQLite may need to create
WAL/-shm sidecar files in the database directory. The systemd unit therefore
allows the `intertop` user to write only there and to the backup directory.

```bash
cd /opt/intertop-training
sudo install -o root -g root -m 0644 \
  deploy/systemd/intertop-training-backup.service \
  /etc/systemd/system/intertop-training-backup.service
sudo install -o root -g root -m 0644 \
  deploy/systemd/intertop-training-backup.timer \
  /etc/systemd/system/intertop-training-backup.timer
# On hosts with the old source-db.conf drop-in, verify it contains only the
# obsolete ReadOnlyPaths setting, then move it aside before reloading systemd.
# sudo mv /etc/systemd/system/intertop-training-backup.service.d/source-db.conf \
#   /etc/systemd/system/intertop-training-backup.service.d/source-db.conf.disabled
sudo systemctl daemon-reload
sudo systemctl enable --now intertop-training-backup.timer
sudo systemctl start intertop-training-backup.service
sudo systemctl status intertop-training-backup.timer --no-pager
ls -l /var/backups/intertop-training
```

The manual backup command in the prior section remains mandatory immediately
before a release or a database-changing operation.

### Enable encrypted offsite backups

The offsite job creates a fresh verified SQLite snapshot, packages it with the
course and upload directories, and encrypts the archive locally with AES-256-GCM
before sending it to S3. The plaintext archive is never written to disk. After
upload it downloads the ciphertext and verifies its size and SHA-256 digest. The S3
credentials must belong to a dedicated service user whose bucket policy permits
only listing, upload, read-back and deletion of expired object versions; do not
grant ordinary object deletion, retention bypass or bucket administration.

The uploader deliberately uses one `PutObject` request instead of an automatic
multipart upload so that the restricted Servercore bucket policy remains
sufficient. A single encrypted backup must remain below the provider's 5 GiB
single-upload limit; the job fails safely before upload if that limit is reached.
After each verified upload, the job deletes only versions below the `daily/`
prefix that are older than the configured retention period. Keep the period
above the bucket's 30-day Object Lock duration. Grant the service user
`DeleteObjectVersion`, but never `DeleteObject` or
`BypassGovernanceRetention`.

Create `/etc/intertop-training/offsite-backup.env` as `root:intertop` mode
`0640`. Store the following values outside Git:

```text
INTERTOP_S3_ENDPOINT=https://s3.kz-1.srvstorage.kz
INTERTOP_S3_REGION=kz-1
INTERTOP_S3_BUCKET=mentorconnect-prod-backups-ACCOUNT_SUFFIX
INTERTOP_S3_ACCESS_KEY_ID=REDACTED
INTERTOP_S3_SECRET_ACCESS_KEY=REDACTED
INTERTOP_BACKUP_ENCRYPTION_KEY=URLSAFE_BASE64_ENCODED_32_BYTES
INTERTOP_BACKUP_RETENTION_DAYS=35
```

Generate the encryption key once on a trusted machine and retain an offline copy
in the approved password manager. Losing this key makes every offsite backup
unrecoverable. Do not store the encryption key in S3 or in the repository.

```bash
python3 -c 'import base64,secrets; print(base64.urlsafe_b64encode(secrets.token_bytes(32)).decode())'
sudo install -d -o intertop -g intertop -m 0700 \
  /var/backups/intertop-training/offsite-work
sudo install -o root -g root -m 0644 \
  deploy/systemd/intertop-training-offsite-backup.service \
  /etc/systemd/system/intertop-training-offsite-backup.service
sudo install -o root -g root -m 0644 \
  deploy/systemd/intertop-training-offsite-backup.timer \
  /etc/systemd/system/intertop-training-offsite-backup.timer
sudo systemctl daemon-reload
sudo systemctl start intertop-training-offsite-backup.service
sudo systemctl status intertop-training-offsite-backup.service --no-pager -l
sudo systemctl enable --now intertop-training-offsite-backup.timer
```

The timer runs after the local backup and daily integrity-audit windows. Verify a
real recovery periodically on an isolated machine: download an encrypted object,
decrypt it with the offline key, inspect the tar manifest, run SQLite
`PRAGMA quick_check`, and validate representative course and upload files.

## 5. Install the Web service

```bash
cd /opt/intertop-training
sudo install -o root -g root -m 0644 \
  deploy/systemd/intertop-training-web.service \
  /etc/systemd/system/intertop-training-web.service
sudo systemctl daemon-reload
sudo systemctl enable --now intertop-training-web
sudo systemctl status intertop-training-web --no-pager
curl --fail http://127.0.0.1:8000/api/v1/health
curl --fail http://127.0.0.1:8000/api/v1/ready
```

If either health check fails, stop here and inspect
`sudo journalctl -u intertop-training-web -n 100 --no-pager`. Do not expose Nginx
until the loopback readiness check is green.

## 6. Obtain TLS and configure Nginx

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
curl --fail --location https://staging.example.com/api/v1/health
curl --fail --location https://staging.example.com/api/v1/ready
```

Use the provider's managed TLS equivalent when Nginx is not the public proxy;
still preserve the `Host` and `X-Forwarded-Proto` headers and set
`INTERTOP_FORWARDED_ALLOW_IPS` to the proxy's real, specific IP addresses.

## 7. Release and rollback

For every release: take a backup, run both audits, update to an approved commit,
install dependencies if required, restart the service, then run
`/api/v1/health` and `/api/v1/ready` through HTTPS. Complete the real
platform-owner acceptance flow only after these checks pass.

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

Run `/api/v1/ready` after the restart and keep the safety backup until the
smoke test is complete.
