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

| Option | Description |
|--------|-------------|
| `blackout_time_limit` | Time (seconds) to wait before confirming power is truly lost. Set in the SH-RPi daemon config, not here. Lower = faster shutdown but more sensitive to glitches. Recommended: 0.5-1.0s |

The add-on requires no configuration — it automatically monitors the Sailor Hat via I2C and triggers shutdown on power loss.

## How It Works

1. `shrpid` daemon monitors the SH-RPi hardware via I2C
2. When external power drops, supercapacitors take over
3. After the blackout timer expires, `shrpid` executes `/custom-poweroff.sh`
4. The script runs `sync` (flush filesystem buffers) then `dbus-send PowerOff`
5. systemd sends SIGTERM to all processes simultaneously and unmounts filesystems
6. Power is cut — filesystem remains clean for next boot

## Troubleshooting

- **ext4 journal replay on boot**: Normal and expected after any unclean shutdown
- **No shutdown on power loss**: Check I2C device access (`/dev/i2c-1`), verify `shrpid` is running in addon logs
- **Shutdown too slow**: Reduce `blackout_time_limit` in the SH-RPi daemon (see hardware docs)

## Links

- [Sailor Hat for Raspberry Pi](https://docs.hatlabs.fi/sh-rpi/docs/)
- [GitHub Repository](https://github.com/eburi/ha_addon_sh_rpi_daemon)
- [Report an Issue](https://github.com/eburi/ha_addon_sh_rpi_daemon/issues)
