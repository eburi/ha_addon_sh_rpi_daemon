#!/usr/bin/env python3
"""Publish SH-RPi telemetry to Home Assistant over MQTT discovery.

shrpid already knows everything worth knowing about the HAT -- input voltage,
supercapacitor voltage, input current, MCU temperature and the power state --
but it keeps all of it on a unix socket where nothing records it. Without
history a degrading supercapacitor bank is invisible until the day it fails to
carry a shutdown, so everything is published with `state_class: measurement`,
which is what makes the recorder keep long-term statistics.

Discovery configs are retained, so the entities survive a Home Assistant
restart. Availability is a retained LWT topic, so the entities go unavailable
when this process, the broker connection or shrpid itself dies, rather than
silently freezing at the last value they happened to see.

Broker credentials come from the Supervisor's mqtt service, which needs
`services: - mqtt:want` in config.yaml. MQTT_HOST/MQTT_PORT/MQTT_USERNAME/
MQTT_PASSWORD override it, for running this by hand outside the add-on.

Nothing here is allowed to take the daemon down: this runs as a separate
process and every failure path is a retry, never an exit.
"""

import json
import os
import signal
import socket
import sys
import time
import urllib.error
import urllib.request

import paho.mqtt.client as mqtt

SHRPID_SOCKET = os.environ.get("SHRPID_SOCKET", "/var/run/shrpid.sock")
NODE = os.environ.get("SHRPI_NODE_ID", "shrpi")
INTERVAL = float(os.environ.get("SENSOR_INTERVAL", "10"))

# One HAT per Pi, so the node id is both the topic root and the discovery
# node id -- "shrpi/state", "homeassistant/sensor/shrpi/input_voltage/config".
STATE_TOPIC = f"{NODE}/state"
AVAILABILITY_TOPIC = f"{NODE}/availability"
DISCOVERY_PREFIX = os.environ.get("MQTT_DISCOVERY_PREFIX", "homeassistant")

# (component, key, name, value_template, extra discovery keys)
ENTITIES = [
    ("sensor", "input_voltage", "Input voltage", "{{ value_json.V_in }}",
     {"device_class": "voltage", "unit_of_measurement": "V",
      "state_class": "measurement", "suggested_display_precision": 2}),
    ("sensor", "supercap_voltage", "Supercapacitor voltage", "{{ value_json.V_supercap }}",
     {"device_class": "voltage", "unit_of_measurement": "V",
      "state_class": "measurement", "suggested_display_precision": 2}),
    ("sensor", "input_current", "Input current", "{{ value_json.I_in }}",
     {"device_class": "current", "unit_of_measurement": "A",
      "state_class": "measurement", "suggested_display_precision": 3}),
    ("sensor", "mcu_temperature", "MCU temperature", "{{ value_json.T_mcu }}",
     {"device_class": "temperature", "unit_of_measurement": "°C",
      "state_class": "measurement", "suggested_display_precision": 1}),
    # Left as a plain sensor rather than an enum: the state list belongs to the
    # shrpid version installed in the image, and a newer one adding a state
    # should not start logging template errors in Home Assistant.
    ("sensor", "state", "State", "{{ value_json.state }}",
     {"icon": "mdi:state-machine"}),
    ("binary_sensor", "5v_output", "5V output", "{{ value_json.en5v }}",
     {"payload_on": "on", "payload_off": "off",
      "device_class": "power", "entity_category": "diagnostic"}),
    ("binary_sensor", "watchdog", "Watchdog", "{{ value_json.watchdog }}",
     {"payload_on": "on", "payload_off": "off",
      "entity_category": "diagnostic"}),
]


def log(msg):
    print(f"[shrpi_sensors] {msg}", flush=True)


def shrpid_get(path):
    """GET a path from shrpid's unix socket and return the decoded JSON."""
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    s.settimeout(5)
    try:
        s.connect(SHRPID_SOCKET)
        s.sendall(f"GET {path} HTTP/1.0\r\nHost: localhost\r\n\r\n".encode())
        buf = b""
        while True:
            chunk = s.recv(4096)
            if not chunk:
                break
            buf += chunk
    finally:
        s.close()
    head, _, body = buf.partition(b"\r\n\r\n")
    if b" 200 " not in head.split(b"\r\n")[0]:
        raise RuntimeError(f"shrpid {path} returned {head.splitlines()[0]!r}")
    return json.loads(body.decode())


def broker_config():
    """Broker details from the environment, else from the Supervisor."""
    if os.environ.get("MQTT_HOST"):
        return {
            "host": os.environ["MQTT_HOST"],
            "port": int(os.environ.get("MQTT_PORT", "1883")),
            "username": os.environ.get("MQTT_USERNAME", ""),
            "password": os.environ.get("MQTT_PASSWORD", ""),
        }

    token = os.environ.get("SUPERVISOR_TOKEN")
    if not token:
        raise RuntimeError("no SUPERVISOR_TOKEN and no MQTT_HOST")
    req = urllib.request.Request(
        "http://supervisor/services/mqtt",
        headers={"Authorization": f"Bearer {token}"},
    )
    data = json.load(urllib.request.urlopen(req, timeout=10))["data"]
    return {
        "host": data["host"],
        "port": int(data["port"]),
        "username": data.get("username", ""),
        "password": data.get("password", ""),
    }


def make_client(cfg):
    try:  # paho-mqtt 2.x
        client = mqtt.Client(
            mqtt.CallbackAPIVersion.VERSION2, client_id=f"shrpi-sensors-{NODE}"
        )
    except AttributeError:  # paho-mqtt 1.x
        client = mqtt.Client(client_id=f"shrpi-sensors-{NODE}")
    if cfg["username"]:
        client.username_pw_set(cfg["username"], cfg["password"])
    client.will_set(AVAILABILITY_TOPIC, "offline", qos=1, retain=True)
    client.reconnect_delay_set(min_delay=1, max_delay=60)
    return client


def publish_discovery(client, versions):
    device = {
        "identifiers": [f"shrpi_{NODE}"],
        "name": "Sailor HAT (SH-RPi)",
        "manufacturer": "Hat Labs",
        "model": "SH-RPi v" + versions.get("hardware_version", "?"),
        "sw_version": "firmware {} / shrpid {}".format(
            versions.get("firmware_version", "?"),
            versions.get("daemon_version", "?"),
        ),
    }
    for component, key, name, template, extra in ENTITIES:
        payload = {
            "name": name,
            "unique_id": f"shrpi_{NODE}_{key}",
            "state_topic": STATE_TOPIC,
            "value_template": template,
            "availability_topic": AVAILABILITY_TOPIC,
            "device": device,
        }
        payload.update(extra)
        client.publish(
            f"{DISCOVERY_PREFIX}/{component}/{NODE}/{key}/config",
            json.dumps(payload),
            qos=1,
            retain=True,
        )
    log(f"published discovery for {len(ENTITIES)} entities under {DISCOVERY_PREFIX}/")


def read_hat():
    values = shrpid_get("/values")
    state = shrpid_get("/state")
    return {
        "V_in": round(values["V_in"], 3),
        "V_supercap": round(values["V_supercap"], 3),
        "I_in": round(values["I_in"], 4),
        # shrpid reports the MCU temperature in kelvin.
        "T_mcu": round(values["T_mcu"] - 273.15, 2),
        "state": state["state"],
        "en5v": "on" if state["5v_output_enabled"] else "off",
        "watchdog": "on" if state["watchdog_enabled"] else "off",
    }


def main():
    if INTERVAL <= 0:
        log("sensor_interval is 0, telemetry publishing disabled")
        return

    # shrpid creates the socket at startup; run.sh backgrounds us first.
    for _ in range(60):
        if os.path.exists(SHRPID_SOCKET):
            break
        time.sleep(1)
    else:
        raise RuntimeError(f"{SHRPID_SOCKET} did not appear")

    cfg = broker_config()
    versions = shrpid_get("/version")
    client = make_client(cfg)
    client.connect(cfg["host"], cfg["port"], keepalive=max(60, int(INTERVAL * 3)))
    client.loop_start()
    log(f"connected to {cfg['host']}:{cfg['port']} as {cfg['username'] or '<anonymous>'}")

    # A killed process lets the LWT mark the entities unavailable, but a clean
    # stop closes the connection properly and the LWT never fires -- so say it.
    def goodbye(signum, frame):
        log("stopping, marking unavailable")
        client.publish(AVAILABILITY_TOPIC, "offline", qos=1, retain=True)
        client.disconnect()
        sys.exit(0)

    signal.signal(signal.SIGTERM, goodbye)
    signal.signal(signal.SIGINT, goodbye)

    publish_discovery(client, versions)
    # Republish discovery when Home Assistant restarts and asks everyone to.
    client.subscribe(f"{DISCOVERY_PREFIX}/status", qos=1)
    client.message_callback_add(
        f"{DISCOVERY_PREFIX}/status",
        lambda c, u, m: (
            publish_discovery(c, versions)
            if m.payload == b"online"
            else None
        ),
    )

    available = None
    while True:
        try:
            payload = read_hat()
        except Exception as exc:
            if available is not False:
                log(f"cannot read shrpid, marking unavailable: {exc}")
                client.publish(AVAILABILITY_TOPIC, "offline", qos=1, retain=True)
                available = False
        else:
            client.publish(STATE_TOPIC, json.dumps(payload), qos=0, retain=True)
            if available is not True:
                client.publish(AVAILABILITY_TOPIC, "online", qos=1, retain=True)
                available = True
        time.sleep(INTERVAL)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        # run.sh restarts us; exiting loudly beats wedging silently.
        log(f"fatal: {type(exc).__name__}: {exc}")
        sys.exit(1)
