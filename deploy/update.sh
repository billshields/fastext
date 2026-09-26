#!/bin/bash
# Deploy the latest code from GitHub:  sudo bash /srv/fastext/deploy/update.sh
set -euo pipefail

# Everything runs from inside main, so bash has read the whole script before
# git pull can rewrite this file underneath it
main() {
    cd /srv/fastext
    sudo -u fastext git pull --ff-only
    sudo -u fastext venv/bin/pip install --no-cache-dir -r requirements.txt
    sudo -u fastext venv/bin/python manage.py migrate --noinput
    sudo -u fastext venv/bin/python manage.py collectstatic --noinput
    cp deploy/systemd/fastext-web.service deploy/systemd/fastext-worker.service /etc/systemd/system/
    systemctl daemon-reload
    systemctl restart fastext-web fastext-worker
    echo "Deployed $(sudo -u fastext git log -1 --format='%h %s')"
}

main "$@"
