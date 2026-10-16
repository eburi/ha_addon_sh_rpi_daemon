# Home Assistant Add-on: SH-RPi Daemon

Safely shuts down Home Assistant when power is lost using the Sailor Hat for Raspberry Pi's supercapacitor backup.

## Why This Add-on?

The Sailor Hat for Raspberry Pi (SH-RPi) provides 20-30 seconds of backup power via supercapacitors when DC power fails. This add-on detects power loss and initiates a safe shutdown — **fast enough** to complete before the supercapacitors drain.

Uses direct `dbus-send PowerOff` to systemd instead of the slow Supervisor API, ensuring the filesystem sync completes within the supercapacitor runtime window.

## Hardware

- **Sailor Hat for Raspberry Pi** (HW 2.0.1 / FW 2.0.6 / shrpid 2.2.6+)
- Raspberry Pi 5 recommended
- NVMe SSD recommended (faster shutdown than SD card)

## Installation

### From GitHub (Latest)

1. Add this repository to Home Assistant:
   **https://github.com/eburi/ha_addon_sh_rpi_daemon**

2. Install the "SH Rpi Daemon for Sailor HAT" add-on

### Local Development

```bash
./local_deploy.sh
```

Deploys to the default HA instance (192.168.46.222). See `./local_deploy.sh -h` for options.

## Configuration

| Option | Default | Description |
|--------|---------|-------------|
| `blackout_time_limit` | `1.0` | Seconds of input undervoltage before shutdown is triggered. This is time spent *not* shutting down, taken out of the supercapacitor budget, so keep it short. `shrpid`'s own default is 3.0s, which is a large slice of the runtime a loaded Pi 5 actually gets. |
| `blackout_voltage_limit` | `9.0` | Input volts below which power counts as lost. The SH-RPi accepts 9–32V in, so 9.0 is the bottom of the usable range. Raise it on a 12V system that sags under load if you want an earlier shutdown. |
| `sensor_interval` | `10` | Seconds between telemetry publishes. `0` disables publishing. |

Lower `blackout_time_limit` means a faster shutdown but more sensitivity to a
brief sag. On a 24V system the input would have to drop by two thirds to reach
9V, so a short limit is safe; on 12V, measure before trusting it.

## Telemetry

The add-on publishes the HAT's state to Home Assistant over MQTT discovery,
which requires an MQTT broker add-on (e.g. Mosquitto). Without one the add-on
logs a warning and carries on doing its real job — the shutdown path does not
depend on MQTT.

| Entity | Unit |
|--------|------|
| `sensor.sailor_hat_sh_rpi_input_voltage` | V |
| `sensor.sailor_hat_sh_rpi_supercapacitor_voltage` | V |
| `sensor.sailor_hat_sh_rpi_input_current` | A |
| `sensor.sailor_hat_sh_rpi_mcu_temperature` | °C |
| `sensor.sailor_hat_sh_rpi_state` | — |
| `binary_sensor.sailor_hat_sh_rpi_5v_output` | — |
| `binary_sensor.sailor_hat_sh_rpi_watchdog` | — |

The numeric entities carry `state_class: measurement`, so the recorder keeps
long-term statistics. **This is the point of the feature:** supercapacitors
degrade quietly, and a bank that no longer carries a shutdown still reads a
healthy 8.8V while shore power is present, because that figure is the regulated
bus the first-stage buck holds up. A months-long history of
`supercapacitor_voltage` and `input_current` is what makes the decay visible
before the day it matters.

`sensor.sailor_hat_sh_rpi_state` reports the HAT's own state machine. The ones
worth recognising:

| State | Meaning |
|-------|---------|
| `POWER_ON_5V_ON` | normal running, input power present |
| `POWER_OFF_5V_ON` | **input power gone, running on the supercapacitors** |
| `ENTER_SHUTDOWN` / `SHUTDOWN` | the HAT has been told to cut power |
| `WATCHDOG_REBOOT` | `shrpid` stopped petting the watchdog and the HAT power-cycled the Pi |

Seeing `POWER_OFF_5V_ON` in the history after a power cut is the proof that the
supercapacitors carried the Pi. Never seeing it means they did not.

Entities go `unavailable` if the publisher, the broker connection or `shrpid`
itself stops, rather than freezing at their last value.

## How It Works

1. `shrpid` daemon monitors the SH-RPi hardware via I2C
2. When external power drops, supercapacitors take over
3. After the blackout timer expires, `shrpid` executes `/custom-poweroff.sh`
4. The script runs `sync` (flush filesystem buffers) then `dbus-send PowerOff`
5. systemd sends SIGTERM to all processes simultaneously and unmounts filesystems
6. Power is cut — filesystem remains clean for next boot

## Shutdown Log

Every power-loss shutdown is recorded to `/data/shutdown.log` inside the add-on container. This file persists across reboots. On the next startup, the add-on prints the previous shutdown log to the add-on logs and archives it to `/data/shutdown.log.prev`.

Example output in the add-on logs after a power-loss event:

```
========================================
PREVIOUS SHUTDOWN LOG FOUND:
========================================
  2026-03-16 18:56:58 === POWER LOSS DETECTED — initiating emergency shutdown ===
  2026-03-16 18:56:58 Uptime: 13119.00 35765.42
  2026-03-16 18:56:58 Flushing filesystem buffers (sync)...
  2026-03-16 18:56:58 Sync completed
  2026-03-16 18:56:58 Sending PowerOff via D-Bus to systemd...
  2026-03-16 18:56:58 PowerOff command sent. Waiting for systemd to shut down...
========================================
```

If the log is truncated (e.g., missing "Sync completed" or "PowerOff command sent"), it indicates the supercapacitors drained before that step completed.

## Troubleshooting

- **ext4 journal replay on boot**: Normal and expected after any unclean shutdown
- **No shutdown on power loss**: Check I2C device access (`/dev/i2c-1`), verify `shrpid` is running in addon logs
- **Shutdown too slow**: Reduce `blackout_time_limit` in the add-on options
- **Shutdown log truncated**: The supercap runtime was insufficient — check hardware connections and capacitor health
- **No shutdown log at all after a power cut, and the journal just stops**: `shrpid` never reached its shutdown state, so the 5V rail went away in less than `blackout_time_limit`. That is a holdover failure, not a configuration one — a healthy bank carries a loaded Pi 5 for roughly 15-20s. Check `sensor.sailor_hat_sh_rpi_state` history for `POWER_OFF_5V_ON`: if it never appears, the supercapacitors are not carrying the load. A bank that is degraded or electrically disconnected still reports ~8.8V while input power is present

## Links

- [Sailor Hat for Raspberry Pi](https://docs.hatlabs.fi/sh-rpi/docs/)
- [GitHub Repository](https://github.com/eburi/ha_addon_sh_rpi_daemon)
- [Report an Issue](https://github.com/eburi/ha_addon_sh_rpi_daemon/issues)
