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

DEAMON="$(which shrpid)"

bashio::log.info "Starting Sailor HAT deamon using $DEAMON...."

echo "I2C devices:"
echo "--------------------------------"
find /dev -name "*i2c*"
echo "--------------------------------"

# Start gateway
exec $DEAMON
