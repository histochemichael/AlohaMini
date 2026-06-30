# Command Templates

Replace every value in angle brackets before running.

## Raspberry Pi

### Terminal 1: base and lift receiver

```bash
cd <PATH_TO_AlohaMini>/AlohaMini1/teleoperate/pi
python3 -u aloha_pi_follower_agent_pyserial.py \
  --servo-port <BASE_LIFT_PORT> \
  --port 9000 \
  --front-id <FRONT_BASE_SERVO_ID> \
  --back-left-id <BACK_LEFT_BASE_SERVO_ID> \
  --back-right-id <BACK_RIGHT_BASE_SERVO_ID> \
  --lift-id <LIFT_SERVO_ID> \
  --setup-velocity-mode
```

The working prototype used base servo IDs `9`, `8`, `10` and lift ID `11`, but verify your own wiring.

### Terminal 2: left follower arm receiver

```bash
cd <PATH_TO_AlohaMini>/AlohaMini1/teleoperate/pi
python3 -u so101_follower_http_agent.py \
  --follower-port <LEFT_FOLLOWER_PORT> \
  --port 9011 \
  --robot-id <LEFT_FOLLOWER_CALIBRATION_ID> \
  --max-relative-target 10 \
  --activation-threshold 1.0
```

### Terminal 3: right follower arm receiver

```bash
cd <PATH_TO_AlohaMini>/AlohaMini1/teleoperate/pi
python3 -u so101_follower_http_agent.py \
  --follower-port <RIGHT_FOLLOWER_PORT> \
  --port 9012 \
  --robot-id <RIGHT_FOLLOWER_CALIBRATION_ID> \
  --max-relative-target 10 \
  --activation-threshold 1.0
```

### Optional Terminal 4: camera dashboard

Edit `pi/aloha_camera_dashboard.py` first and replace the `CAMERAS` paths with your own `/dev/v4l/by-path/...` names.

```bash
cd <PATH_TO_AlohaMini>/AlohaMini1/teleoperate/pi
python3 -u aloha_camera_dashboard.py --host 0.0.0.0 --port 9100 --width 640 --height 480 --fps 5
```

Open from the PC at `http://<PI_IP>:9100`.

## PC

### Terminal 1: base, lift, and steering sender

```bat
conda activate <PEDAL_ENV>
cd <PATH_TO_AlohaMini>\AlohaMini1\teleoperate\pc
python combined_gyro_pedal_control_remote.py --host 0.0.0.0 --pc-host-hint <PC_WIFI_IP> --robot-host <PI_IP> --robot-port 9000 --web-port 8765 --turn-speed 600 --invert-turn --base-forward-key d --base-backward-key f --lift-up-key a --lift-down-key s --base-speed 3000 --lift-speed 1000 --stream-commands
```

Phone gyro steering page:

```text
http://<PC_WIFI_IP>:8765
```

Face steering alternative:

```bat
python combined_gyro_pedal_control_remote.py --robot-host <PI_IP> --robot-port 9000 --web-port 8765 --turn-speed 600 --invert-turn --base-forward-key d --base-backward-key f --lift-up-key a --lift-down-key s --base-speed 1500 --lift-speed 1000 --stream-commands --steering-mode face --face-camera 0 --face-deadband 15 --face-max-yaw 40 --face-smoothing 0.2 --face-preview --request-timeout 2.0
```

### Terminal 2: left leader arm sender

```bat
conda activate <LEROBOT_ENV>
cd <PATH_TO_AlohaMini>\AlohaMini1\teleoperate\pc
python so101_leader_http_sender.py --leader-port <LEFT_LEADER_COM_PORT> --leader-id <LEFT_LEADER_CALIBRATION_ID> --robot-url http://<PI_IP>:9011 --fps 10
```

### Terminal 3: right leader arm sender

```bat
conda activate <LEROBOT_ENV>
cd <PATH_TO_AlohaMini>\AlohaMini1\teleoperate\pc
python so101_leader_http_sender.py --leader-port <RIGHT_LEADER_COM_PORT> --leader-id <RIGHT_LEADER_CALIBRATION_ID> --robot-url http://<PI_IP>:9012 --fps 10
```

## Status checks

On the Pi:

```bash
curl http://127.0.0.1:9000/status
curl http://127.0.0.1:9011/status
curl http://127.0.0.1:9012/status
```

On the PC:

```bat
curl http://<PI_IP>:9000/status
curl http://<PI_IP>:9011/status
curl http://<PI_IP>:9012/status
powershell -Command "Test-NetConnection <PI_IP> -Port 9000"
powershell -Command "Test-NetConnection <PI_IP> -Port 9011"
powershell -Command "Test-NetConnection <PI_IP> -Port 9012"
```
