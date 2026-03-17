#!/usr/bin/with-contenv bashio
set -e

# --- Persistent shutdown log (survives reboot via /data/) ---
SHUTDOWN_LOG="/data/shutdown.log"

log_persist() {
  local msg="$(date '+%Y-%m-%d %H:%M:%S') $1"
  bashio::log.info "$1"
  echo "$msg" >> "$SHUTDOWN_LOG"
  sync -f "$SHUTDOWN_LOG" 2>/dev/null || true
}

log_persist "=== POWER LOSS DETECTED — initiating emergency shutdown ==="
log_persist "Uptime: $(cat /proc/uptime)"

# 1. Emergency sync: flush all dirty filesystem buffers to disk immediately.
#    This forces an ext4 journal commit so the filesystem can recover cleanly
#    even if the supercap runs out before systemd finishes its shutdown sequence.
log_persist "Flushing filesystem buffers (sync)..."
sync
log_persist "Sync completed"

# 2. Trigger systemd PowerOff via D-Bus (bypasses Supervisor container teardown).
#    The Supervisor API path (bashio::host.shutdown) stops containers sequentially,
#    which takes 40+ seconds — far longer than the ~20s supercap runtime.
#    Calling systemd directly via D-Bus sends SIGTERM to all processes simultaneously
#    and performs a filesystem unmount/sync pass, completing in ~15-20 seconds.
log_persist "Sending PowerOff via D-Bus to systemd..."
dbus-send --system --print-reply \
  --dest=org.freedesktop.login1 \
  /org/freedesktop/login1 \
  org.freedesktop.login1.Manager.PowerOff \
  boolean:false

log_persist "PowerOff command sent. Waiting for systemd to shut down..."
