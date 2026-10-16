#!/usr/bin/with-contenv bashio
set -e

SHUTDOWN_LOG="/data/shutdown.log"

# --- Report previous shutdown event (if any) ---
if [ -f "$SHUTDOWN_LOG" ]; then
  bashio::log.info "========================================"
  bashio::log.info "PREVIOUS SHUTDOWN LOG FOUND:"
  bashio::log.info "========================================"
  while IFS= read -r line; do
    bashio::log.info "  $line"
  done < "$SHUTDOWN_LOG"
  bashio::log.info "========================================"
  bashio::log.info "Archiving shutdown log to /data/shutdown.log.prev"
  cp "$SHUTDOWN_LOG" "/data/shutdown.log.prev"
  rm "$SHUTDOWN_LOG"
else
  bashio::log.info "No previous shutdown log found — normal startup."
fi

bashio::log.info "Add-on starting at $(date '+%Y-%m-%d %H:%M:%S')"

# bashio::config yields "null" for a key an older options.json never set, and
# "null" through `set -e` would stop the add-on from starting at all -- i.e. no
# power protection. Fall back to the config.yaml defaults instead.
cfg() {
  if bashio::config.has_value "$1"; then bashio::config "$1"; else echo "$2"; fi
}

BLACKOUT_TIME_LIMIT="$(cfg 'blackout_time_limit' '1.0')"
BLACKOUT_VOLTAGE_LIMIT="$(cfg 'blackout_voltage_limit' '9.0')"
SENSOR_INTERVAL="$(cfg 'sensor_interval' '10')"

DEAMON="$(which shrpid)"

echo "I2C devices:"
echo "--------------------------------"
find /dev -name "*i2c*"
echo "--------------------------------"

# --- Telemetry publisher ---
# Backgrounded and supervised here rather than run by shrpid: it must never be
# able to stop the daemon from seeing a blackout. shrpid is the foreground
# process, so if it dies the container dies and the watchdog restarts us.
if [ "$SENSOR_INTERVAL" -gt 0 ]; then
  if bashio::services.available "mqtt"; then
    bashio::log.info "Publishing HAT telemetry every ${SENSOR_INTERVAL}s over MQTT discovery"
    (
      export SENSOR_INTERVAL
      while true; do
        python3 /shrpi_sensors.py || bashio::log.warning "telemetry publisher exited, retrying in 30s"
        sleep 30
      done
    ) &
  else
    bashio::log.warning "No MQTT broker available — HAT telemetry will not be published."
    bashio::log.warning "Install and start an MQTT broker add-on to get the sensors."
  fi
else
  bashio::log.info "sensor_interval is 0 — HAT telemetry publishing disabled"
fi

bashio::log.info "Starting Sailor HAT deamon using $DEAMON...."
bashio::log.info "  blackout time limit:    ${BLACKOUT_TIME_LIMIT} s"
bashio::log.info "  blackout voltage limit: ${BLACKOUT_VOLTAGE_LIMIT} V"

# Start gateway
exec "$DEAMON" \
  --blackout-time-limit "$BLACKOUT_TIME_LIMIT" \
  --blackout-voltage-limit "$BLACKOUT_VOLTAGE_LIMIT"
