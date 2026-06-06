# AlohaMini2
[![Join our Discord](https://img.shields.io/badge/Discord-Join%20chat-blue)](https://discord.gg/CacMUBaFgJ) [![Follow on X](https://img.shields.io/twitter/follow/liyitengx?style=social)](https://x.com/liyitengx)

AlohaMini2 is a dual-arm mobile robot with a motorized vertical lift — a major generational upgrade over AlohaMini1 while keeping the self-build BOM under $1,000.  

Fully 3D-printable on a Bambu P2S, built for embodied AI research, and priced for anyone serious about real-world manipulation.

> Assemble at home in ~120 minutes. Train or deploy with LeRobot.


## Updates

- [2026-06-06] AlohaMini2 released — 70 kg base load, 30 kg lift, 1 kg arm payload, 6+1 DoF, 52 cm reach, under $1,000 self-build BOM
- [2026-02-26] Fine-tuning and deployment guide for Pi 0.5 on AlohaMini (`examples/pi0.5_openpi`)
- [2025-12-18] URDF and simulation assets available (`AlohaMini1/simulation/src/Aloha/`)
- [2025-11-27] STEP (CAD) files available (`AlohaMini1/hardware/mobile_base/step/`)


## What's New in AlohaMini2

### Architecture

| | AlohaMini | AlohaMini2 |
|---|---|---|
| Arm system | SO-ARM100 / SO-ARM101 | AM-ARM200 |
| Mobile base system | mobile_base1 | mobile_base2 |
| Printer requirement | Large-format FDM (>= 380 mm bed) | Bambu P2S (consumer-grade) |

### Performance

| | AlohaMini | AlohaMini2 |
|---|---|---|
| Base max load | 10 kg | 70 kg  |
| Lift capacity | 5 kg | 30 kg |
| Lift stability | Standard | Significantly reinforced |
| Arm payload | 0.3 kg | 1 kg |
| Arm reach | 40 cm | 52 cm |
| Arm DoF | 5+1 | 6+1 |
| Cameras | 5 | 5 (forward, backward, chest, dual wrist) |

AlohaMini2 is LeRobot-ready out of the box and remains fully open-source — hardware CAD, URDF, and software included.


## Gallery

<p align="center">
  <img src="AlohaMini1/docs/media/alohamini_git.png" width="100%"/>
</p>


## Bill of Materials (BOM)

| Component | Model / Notes | Qty | Unit Price (USD) |
|-----------|---------------|-----|------------------|
| Servo — standard | Feetech STS-3215 (12V, follower arms + base) | 11 | ~$16 |
| Servo — high-torque | Feetech STS-3095 (12V 95 kg·cm, lift + arm power joints) | 7 | ~$50 |
| Bus servo controllers | Waveshare | 2 | ~$5 |
| Compute | Raspberry Pi 5 (2 GB) | 1 | ~$93 |
| Cameras | 720p USB, 2.4 mm focal length | 5 | ~$17 |
| Omni wheels | 127 mm (74A) | 3 | ~$40 |
| Battery 12V | 11200 mAh Li-ion | 2 | ~$16 |
| Frame | 3D-printed on Bambu P2S | — | ~4 kg filament |
| **Total** | — | — | **~$950** |

> Full BOM with CN/US buy links: **[AlohaMini2/docs/BOM.md](AlohaMini2/docs/BOM.md)**  
> Compute can be swapped for Jetson Orin Nano or any SBC with USB 3.0.  

## Quick Start

1. **BOM** — review the component list and source parts  
   See **[Bill of Materials](AlohaMini2/docs/BOM.md)**

2. **3D Printing** — print all structural parts (~4 kg filament, Bambu P2S)  
   See **[Print Guide](AlohaMini2/docs/BOM.md#3d-printing)**

3. **Assembly** — build in ~60 minutes (arms pre-assembled)  
   See **[Assembly Guide](AlohaMini2/docs/assembly_guide.md)**

4. **Software setup & teleoperation** — install, connect, control  
   See **[Software Guide](software)**


## Product Line

| Model | Servo System | Chassis | Best For | Official Store (CN) |
|---|---|---|---|---|
| **AlohaMini2** | STS-3215 standard servos | 3D-printed base | Self-build research and development | [Taobao](https://item.taobao.com/item.htm?abbucket=9&id=1015799132286) |
| **AlohaMini2 Pro** | STS-3250 industrial-grade servos | Metal-reinforced base | Higher-duty research and lab use | [Taobao](https://item.taobao.com/item.htm?abbucket=9&id=1015799132286) |


## Contact

Email: liyiteng+github@gmail.com  
WeChat: liyiteng  
Videos & tutorials: Bilibili / YouTube / TikTok


## Team

AlohaMini is created by **Li Yiteng** and **Wu Zhiyong**.


## Acknowledgements

Thanks to the open robotics community:  
**ALOHA · LeKiwi · SO-ARM100 · SO-ARM100-Track-Axis · Pi-0.5 · LeRobot · Hugging Face**


## Support AlohaMini

If you find this project useful:
- Star the repo
- Follow for updates
- Join the community on Discord
