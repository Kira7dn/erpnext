#!/bin/bash
set -e

echo "=== [Letron ERP Minimal] Starting 3-container stack ==="

# 1. Chờ MariaDB và Redis
echo "Waiting for MariaDB ($DB_HOST:$DB_PORT) and Redis ($REDIS_CACHE)..."
wait-for-it -t 120 "$DB_HOST:$DB_PORT"
wait-for-it -t 120 "$REDIS_CACHE"

# 2. Cấu hình Bench toàn cục
echo "Configuring Frappe common settings..."
ls -1 apps > sites/apps.txt || true
bench set-config -g db_host "$DB_HOST"
bench set-config -gp db_port "$DB_PORT"
bench set-config -g redis_cache "redis://$REDIS_CACHE"
bench set-config -g redis_queue "redis://$REDIS_QUEUE"
bench set-config -g redis_socketio "redis://$REDIS_SOCKETIO"
bench set-config -gp developer_mode "$DEVELOPER_MODE"
bench set-config -gp allow_tests "${ALLOW_TESTS:-false}"
bench set-config -gp request_timeout "${REQUEST_TIMEOUT:-120}"
bench set-config -g country "${COUNTRY:-Vietnam}"
bench set-config -g time_zone "${TIMEZONE:-Asia/Ho_Chi_Minh}"
bench set-config -g lang "${LANGUAGE:-vi}"
bench set-config -g currency "${CURRENCY:-VND}"
bench set-config -g default_site "$SITE_NAME"

# 3. Setup site / migrate
if [ ! -f "sites/$SITE_NAME/site_config.json" ]; then
  echo "Site $SITE_NAME does not exist. Initializing new site..."
  bench new-site --mariadb-user-host-login-scope='%' \
    --admin-password="$ADMIN_PASSWORD" \
    --db-root-username="$DB_ROOT_USER" \
    --db-root-password="$MARIADB_ROOT_PASSWORD" \
    --install-app erpnext \
    --install-app "$INTEGRATION_APP" \
    --set-default "$SITE_NAME"
else
  echo "Site $SITE_NAME exists. Running migration..."
  if [ "$INTEGRATION_APP_ENABLED" = "True" ] && ! bench --site "$SITE_NAME" list-apps | grep -Fxq "$INTEGRATION_APP"; then
    bench --site "$SITE_NAME" install-app "$INTEGRATION_APP"
  fi
  bench --site "$SITE_NAME" migrate
fi

# 4. Bootstrap tenant, system config và policy sync
echo "Bootstrapping tenant and syncing policies..."
bench --site "$SITE_NAME" execute letron_api.tenant_bootstrap.run
bench --site "$SITE_NAME" execute letron_api.system_config.sync
bench --site "$SITE_NAME" execute letron_api.policy.sync

# 5. Cấu hình site mapping cho direct API access
echo "Configuring site routing..."
bench use "$SITE_NAME"
ln -sfn "$SITE_NAME" "sites/localhost"
ln -sfn "$SITE_NAME" "sites/127.0.0.1"

# 6. Dependencies are installed in the image at build time.  Startup must not
# reach the package index: a transient network failure must not block ERPNext.
if ! /home/frappe/frappe-bench/env/bin/python -c "import boto3" >/dev/null 2>&1; then
  echo "ERROR: boto3 is missing from the backend image; rebuild the image before starting." >&2
  exit 1
fi

# 7. Chạy background workers & scheduler
echo "Starting background worker & scheduler..."
bench --site "$SITE_NAME" worker --queue short,default,long >> logs/worker.log 2>&1 &
bench --site "$SITE_NAME" schedule >> logs/schedule.log 2>&1 &

# 7. Khởi động Gunicorn Web Server
echo "Starting Gunicorn on 0.0.0.0:8000..."
exec /home/frappe/frappe-bench/env/bin/gunicorn \
  --chdir=/home/frappe/frappe-bench/sites \
  --bind=0.0.0.0:8000 \
  --threads="${GUNICORN_THREADS:-4}" \
  --workers="${GUNICORN_WORKERS:-2}" \
  --worker-class=gthread \
  --worker-tmp-dir=/dev/shm \
  --timeout="${GUNICORN_TIMEOUT:-120}" \
  --preload \
  frappe.app:application
