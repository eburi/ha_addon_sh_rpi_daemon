#!/usr/bin/with-contenv bashio
set -e

bashio::log.info "Power loss detected — initiating emergency shutdown!"

# 1. Emergency sync: flush all dirty filesystem buffers to disk immediately.
#    This forces an ext4 journal commit so the filesystem can recover cleanly
#    even if the supercap runs out before systemd finishes its shutdown sequence.
bashio::log.info "Flushing filesystem buffers (sync)..."
sync

# 2. Trigger systemd PowerOff via D-Bus (bypasses Supervisor container teardown).
#    The Supervisor API path (bashio::host.shutdown) stops containers sequentially,
#    which takes 40+ seconds — far longer than the ~20s supercap runtime.
#    Calling systemd directly via D-Bus sends SIGTERM to all processes simultaneously
#    and performs a filesystem unmount/sync pass, completing in ~15-20 seconds.
bashio::log.info "Sending PowerOff via D-Bus to systemd..."
dbus-send --system --print-reply \
  --dest=org.freedesktop.login1 \
  /org/freedesktop/login1 \
  org.freedesktop.login1.Manager.PowerOff \
  boolean:false

bashio::log.info "PowerOff command sent. Waiting for systemd to shut down..."
