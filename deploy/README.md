# Deploying fastext

A single Ubuntu 24.04 server runs everything:
- **nginx:** HTTPS through Let's Encrypt, and the static files
- **gunicorn:** the Django app, on a local socket
- **Celery:** background jobs
- **Redis:** the queue and the cache
- **MySQL 8.4**

Registration is off, so this is a private instance. You create accounts on the server.

| File | What it is |
|---|---|
| `setup-server.sh` | One-time setup of a fresh server (safe to re-run) |
| `update.sh` | Deploys the latest `master` from GitHub |
| `systemd/` | `fastext-web` (gunicorn) and `fastext-worker` (Celery) services |
| `nginx/fastext.conf` | HTTPS site: static files, proxy to gunicorn |
| `env.example` | The settings `/srv/fastext/.env` holds (the setup script writes the real one) |

## First deploy

1. **Create a server:** Ubuntu 24.04 with 2 GB of RAM, for example a Lightsail 2 GB instance, with a static IP. Open ports 22, 80 and 443 in its firewall.
2. **Point DNS at it:** add an A record for the hostname, e.g. `fastext.app`, with the static IP as its value. Let's Encrypt checks this, so wait until `dig +short fastext.app` returns the IP.
3. **Run the setup script** on the server:
   ```bash
   curl -fsSLO https://raw.githubusercontent.com/billshields/fastext/master/deploy/setup-server.sh
   sudo DOMAIN=fastext.app EMAIL=you@example.com bash setup-server.sh
   ```
   It sets up the following:
   - swap
   - MySQL, Redis and nginx
   - a firewall
   - the `fastext` system user
   - the code in `/srv/fastext`
   - a virtualenv
   - the database, and a `.env` with generated secrets
   - migrations and static files
   - the services, and a certificate that renews itself
4. **Create your account:**
   ```bash
   sudo -u fastext /srv/fastext/venv/bin/python /srv/fastext/manage.py createsuperuser
   ```
   A superuser can also sign in to `/admin/`.
5. **Turn on backups:** enable automatic daily snapshots for the instance (Lightsail: the instance's Snapshots tab). They capture the database and uploaded files.

## Updating

Push to `master`, then run:

```bash
ssh <server> sudo bash /srv/fastext/deploy/update.sh
```

It pulls, installs requirements, migrates, collects static files and restarts both services. Browsers pick up the new JS and CSS immediately, because static filenames are hashed.

If `nginx/fastext.conf` changed, re-run `setup-server.sh` with the same `DOMAIN` and `EMAIL`. It keeps the existing database, `.env` and certificate.

## Running it

```bash
journalctl -u fastext-web -f         # requests and errors
journalctl -u fastext-worker -f      # PDF/EPUB processing and Gutenberg downloads
sudo systemctl restart fastext-web fastext-worker
sudo -u fastext /srv/fastext/venv/bin/python /srv/fastext/manage.py shell
```

**Settings** live in `/srv/fastext/.env` (see `env.example`); restart both services after changing it. For example, `ALLOW_REGISTRATION=True` opens sign-up.

**Login limit:** it allows 10 attempts per minute per address.

**Uploads** go to `/srv/fastext/media`. The web server never serves them; only the worker reads them.
