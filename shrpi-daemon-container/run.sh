#!/usr/bin/with-contenv bashio
set -e

DEAMON="$(which shrpid)"

bashio::log.info "Starting Sailor HAT deamon using $DEAMON...."

echo "I2C devices:"
echo "--------------------------------"
find /dev -name "*i2c*"
echo "--------------------------------"

# Start gateway
exec $DEAMON