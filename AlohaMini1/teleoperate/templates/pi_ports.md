# Pi Port Discovery

Run these on the Raspberry Pi after plugging in the base/lift controller and follower arm controllers:

```bash
ls -l /dev/serial/by-id/
ls -l /dev/ttyACM* /dev/ttyUSB*
```

Prefer `/dev/serial/by-id/...` paths in commands because `/dev/ttyACM0`, `/dev/ttyACM1`, etc. can change after reboot or replugging.

If you need to identify which physical controller is which, plug in one USB controller at a time and run:

```bash
udevadm info -q property -n /dev/ttyACM1 | grep -E 'ID_SERIAL=|ID_SERIAL_SHORT=|ID_MODEL=|ID_VENDOR=|DEVPATH='
ls -l /dev/serial/by-id/
```

Write down the mapping:

```text
BASE_LIFT_PORT=/dev/serial/by-id/...
LEFT_FOLLOWER_PORT=/dev/serial/by-id/...
RIGHT_FOLLOWER_PORT=/dev/serial/by-id/...
```
