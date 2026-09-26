#!/bin/bash
# One-time setup of a fresh Ubuntu 24.04 server for fastext. Safe to re-run: it keeps
# the existing .env, database and certificate, and reinstalls the config files.
#
#   sudo DOMAIN=fastext.app EMAIL=you@example.com bash setup-server.sh
#
# DOMAIN's DNS must already point at this server, because Let's Encrypt checks it.
# Running this agrees to the Let's Encrypt subscriber agreement for EMAIL.
set -euo pipefail

: "${DOMAIN:?Set DOMAIN, e.g. DOMAIN=fastext.app}"
: "${EMAIL:?Set EMAIL, where certificate expiry notices go}"
REPO=${REPO:-https://github.com/billshields/fastext.git}
BRANCH=${BRANCH:-master}
APP=/srv/fastext
MYSQL_APT_CONFIG=mysql-apt-config_0.8.39-1_all.deb

export DEBIAN_FRONTEND=noninteractive

echo '==> Swap'
# 2 GB of RAM gets tight while a large PDF is being processed
if ! swapon --show | grep -q .; then
    fallocate -l 2G /swapfile
    chmod 600 /swapfile
    mkswap /swapfile
    swapon /swapfile
    echo '/swapfile none swap sw 0 0' >> /etc/fstab
fi

echo '==> Packages'
# MySQL 8.4 LTS from Oracle's repo, as in development. Ubuntu 24.04's own 8.0 is past end of life.
if [ ! -f /etc/apt/sources.list.d/mysql.list ]; then
    curl -fsSLo "/tmp/$MYSQL_APT_CONFIG" "https://dev.mysql.com/get/$MYSQL_APT_CONFIG"
    echo 'mysql-apt-config mysql-apt-config/select-server select mysql-8.4-lts' | debconf-set-selections
    echo 'mysql-apt-config mysql-apt-config/select-product select Ok' | debconf-set-selections
    dpkg -i "/tmp/$MYSQL_APT_CONFIG"
fi
apt-get update
apt-get install -y mysql-server libmysqlclient-dev redis-server nginx certbot \
    python3-venv python3-dev build-essential pkg-config git ufw

# Only local connections; the app talks to MySQL over localhost
cat > /etc/mysql/mysql.conf.d/fastext.cnf <<'EOF'
[mysqld]
bind-address = 127.0.0.1
mysqlx = OFF
EOF
systemctl restart mysql

echo '==> Firewall'
ufw allow OpenSSH
ufw allow 'Nginx Full'
ufw --force enable

echo '==> App code'
id fastext &>/dev/null || useradd --system --home-dir "$APP" --shell /usr/sbin/nologin fastext
if [ ! -d "$APP/.git" ]; then
    git clone --branch "$BRANCH" "$REPO" "$APP"
fi
mkdir -p "$APP/media"
chown -R fastext:fastext "$APP"
sudo -u fastext python3 -m venv "$APP/venv"
sudo -u fastext "$APP/venv/bin/pip" install --no-cache-dir --upgrade pip
sudo -u fastext "$APP/venv/bin/pip" install --no-cache-dir -r "$APP/requirements.txt"

echo '==> Database and .env'
if [ ! -f "$APP/.env" ]; then
    DB_PASSWORD=$(openssl rand -hex 24)
    SECRET_KEY=$(openssl rand -base64 60 | tr -dc 'A-Za-z0-9')
    mysql <<SQL
CREATE DATABASE IF NOT EXISTS fastext CHARACTER SET utf8mb4;
CREATE USER IF NOT EXISTS 'fastext'@'localhost' IDENTIFIED BY '$DB_PASSWORD';
ALTER USER 'fastext'@'localhost' IDENTIFIED BY '$DB_PASSWORD';
GRANT ALL PRIVILEGES ON fastext.* TO 'fastext'@'localhost';
SQL
    install -m 600 -o fastext -g fastext /dev/null "$APP/.env"
    cat > "$APP/.env" <<ENV
DJANGO_SETTINGS_MODULE=config.settings.prod
SECRET_KEY=$SECRET_KEY
ALLOWED_HOSTS=$DOMAIN
DB_NAME=fastext
DB_USER=fastext
DB_PASSWORD=$DB_PASSWORD
ENV
fi

echo '==> Migrate and collect static files'
cd "$APP"
sudo -u fastext venv/bin/python manage.py migrate --noinput
sudo -u fastext venv/bin/python manage.py collectstatic --noinput

echo '==> Services'
cp deploy/systemd/fastext-web.service deploy/systemd/fastext-worker.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable fastext-web fastext-worker
systemctl restart fastext-web fastext-worker

echo '==> nginx and HTTPS certificate'
rm -f /etc/nginx/sites-enabled/default
ln -sf /etc/nginx/sites-available/fastext /etc/nginx/sites-enabled/fastext
if [ ! -f "/etc/letsencrypt/live/$DOMAIN/fullchain.pem" ]; then
    # Until there's a certificate, serve only the Let's Encrypt challenge over plain HTTP
    cat > /etc/nginx/sites-available/fastext <<NGINX
server {
    listen 80;
    listen [::]:80;
    server_name $DOMAIN;
    location /.well-known/acme-challenge/ { root /var/www/html; }
}
NGINX
    systemctl reload nginx
    certbot certonly --webroot -w /var/www/html -d "$DOMAIN" \
        --email "$EMAIL" --agree-tos --no-eff-email --non-interactive \
        --deploy-hook 'systemctl reload nginx'
fi
sed "s/__DOMAIN__/$DOMAIN/g" deploy/nginx/fastext.conf > /etc/nginx/sites-available/fastext
nginx -t
systemctl reload nginx

echo
echo "fastext is running at https://$DOMAIN"
echo 'Create your account with:'
echo "  sudo -u fastext $APP/venv/bin/python $APP/manage.py createsuperuser"
