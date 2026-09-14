#!/bin/bash
set -e

echo "=== [Letron ERP] Running one-shot site initialization ==="
wait-for-it -t 120 "$DB_HOST:$DB_PORT"
wait-for-it -t 120 "$REDIS_CACHE"

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

if [ ! -f "sites/$SITE_NAME/site_config.json" ]; then
  bench new-site --mariadb-user-host-login-scope='%' \
    --admin-password="$LETRON_BOOTSTRAP_PASSWORD" \
    --db-root-username="$DB_ROOT_USER" \
    --db-root-password="$LETRON_BOOTSTRAP_PASSWORD" \
    --install-app erpnext \
    --install-app "$INTEGRATION_APP" \
    --set-default "$SITE_NAME"
else
  if [ "$INTEGRATION_APP_ENABLED" = "True" ] && ! bench --site "$SITE_NAME" list-apps | grep -Fxq "$INTEGRATION_APP"; then
    bench --site "$SITE_NAME" install-app "$INTEGRATION_APP"
  fi
  bench --site "$SITE_NAME" migrate
fi

bench --site "$SITE_NAME" execute letron_api.control.policy.sync
bench --site "$SITE_NAME" execute letron_api.control.system_config.sync
bench --site "$SITE_NAME" execute letron_api.control.policy.sync

bench use "$SITE_NAME"
ln -sfn "$SITE_NAME" "sites/localhost"
ln -sfn "$SITE_NAME" "sites/127.0.0.1"
touch "sites/$SITE_NAME/.letron-init-complete"
echo "=== [Letron ERP] One-shot initialization complete ==="
