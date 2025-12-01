#!/usr/bin/with-contenv bashio
set -e

bashio::log.info "Called to power off Home Assistant!!!"

bashio::host.shutdown()