# XREAL VR Stack

A unified installer and launcher for Linux AR/VR components, designed for XREAL Air glasses and similar devices.

## What This Does

This project bundles together the fragmented Linux XR ecosystem into a single, easy-to-use package:

| Component | Purpose |
|-----------|---------|
| **XRLinuxDriver** | Core driver for AR glasses (IMU, display detection) |
| **Breezy Desktop** | Virtual desktop environment with head tracking |
| **Monado** | Open-source OpenXR runtime for VR games |
| **AITrack + OpenTrack** | Webcam-based 6DOF head tracking |
| **Stardust XR** | 3D floating window desktop with skyboxes |
| **VRto3D** | Play VR games on AR glasses via SBS output |
| **ReShade + Depth3D** | Convert 2D games to stereoscopic 3D |

## Quick Install

```bash
# One-liner installation
curl -sSL https://raw.githubusercontent.com/bl4ckj4ck777/VRstack/main/install.sh | bash
```

Or manually:

```bash
git clone https://github.com/bl4ckj4ck777/VRStack.git
cd VRStack
python3 install.py
```

## Installation Options

```bash
# Interactive mode (recommended for first-time setup)
python3 install.py

# Minimal install (just core components)
python3 install.py --minimal

# Full install (everything)
python3 install.py --full

# Specific components only
python3 install.py --components xrlinuxdriver monado stardust-xr

# List available components
python3 install.py --list

# Uninstall everything
python3 install.py --uninstall
```

## Usage

After installation, use the unified launcher:

```bash
# Start AR virtual desktop (Breezy)
xreal-launch desktop

# Enable SBS 3D mode for 3D content
xreal-launch sbs

# Start VR mode with Monado (for OpenXR games)
xreal-launch vr

# Start Stardust XR (floating 3D windows)
xreal-launch stardust

# Launch a game with optimal settings
xreal-launch game portal

# Reset to normal desktop
xreal-launch reset

# Check status
xreal-launch status
```

## Supported Hardware

### AR Glasses
- XREAL Air / Air 2 / Air 2 Pro / Air 2 Ultra
- Rokid Max
- Viture One
- Other SBS-compatible glasses (manual config required)

### Head Tracking
- Any webcam (for 6DOF via AITrack)
- XRLinuxDriver IMU (built-in 3DOF)

### Controllers (Optional)
- PS Move controllers (via PSMoveService)
- Gamepads
- Keyboard/mouse

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     Your Hardware                            │
│  XREAL/Rokid/Viture + Webcam + Keyboard/Gamepad             │
└───────────────────────────┬─────────────────────────────────┘
                            │
┌───────────────────────────▼─────────────────────────────────┐
│                    Tracking Layer                            │
│  XRLinuxDriver (3DOF) ←──┬──→ AITrack/OpenTrack (6DOF)     │
└───────────────────────────┼─────────────────────────────────┘
                            │
┌───────────────────────────▼─────────────────────────────────┐
│                    Runtime Layer                             │
│  ┌─────────────┐  ┌──────────────┐  ┌────────────────────┐ │
│  │   Monado    │  │  SteamVR +   │  │  Direct SBS Mode   │ │
│  │  (OpenXR)   │  │   VRto3D     │  │  (Breezy Desktop)  │ │
│  └─────────────┘  └──────────────┘  └────────────────────┘ │
└───────────────────────────┬─────────────────────────────────┘
                            │
┌───────────────────────────▼─────────────────────────────────┐
│                   Application Layer                          │
│  ┌─────────────┐  ┌──────────────┐  ┌────────────────────┐ │
│  │  VR Games   │  │  2D Games +  │  │   Stardust XR      │ │
│  │  (OpenXR)   │  │  Depth3D     │  │  (3D Desktop)      │ │
│  └─────────────┘  └──────────────┘  └────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
```

## Modes Explained

### Desktop Mode (Breezy)
Standard AR virtual desktop. Your screen floats in front of you with head tracking.
- Best for: Productivity, video watching, general use
- Tracking: 3DOF rotation

### SBS 3D Mode  
Side-by-side stereoscopic output. Each eye sees a different image for depth perception.
- Best for: 3D movies, games with Depth3D shader
- Resolution: 3840x1080 (1920x1080 per eye)

### VR Mode (Monado)
Full OpenXR runtime. Games see your glasses as a VR headset.
- Best for: Native VR games, OpenXR applications
- Tracking: 3DOF (or 6DOF with webcam tracking enabled)

### Stardust XR Mode
True 3D desktop environment with floating windows, skyboxes, and spatial widgets.
- Best for: Immersive computing, the "future of desktop"
- Requires: Monado, may need VR controllers for best experience

## Troubleshooting

### Glasses not detected
```bash
# Check USB connection
lsusb | grep -i "3318\|rokid\|viture"

# Reload driver
xr_driver_cli -d && xr_driver_cli -e
```

### SBS mode has wrong scale
```bash
# Check current display config
xrandr --listmonitors

# Manual fix
xrandr --output DP-9 --mode 3840x1080 --scale 1x1
```

### Monado won't start
```bash
# Check OpenXR runtime config
cat ~/.config/openxr/1/active_runtime.json

# Test with xrgears
xrgears
```

### Head tracking is drifting
```bash
# Recalibrate by tapping glasses 3 times
# Or run:
xr_driver_cli -c
```

## Configuration

Config files are stored in `~/.config/VRStack/`:

- `displays.conf` - Display names and preferences
- `tracking.conf` - Head tracking settings
- `games.conf` - Per-game configurations

## Contributing

This project aims to unify the Linux XR experience. Contributions welcome:

1. Additional device support
2. Distro-specific fixes
3. Component integrations
4. Documentation improvements

## Credits

This installer wraps and integrates work from:

- [XRLinuxDriver](https://github.com/wheaney/XRLinuxDriver) by wheaney
- [Breezy Desktop](https://github.com/wheaney/breezy-desktop) by wheaney  
- [Monado](https://monado.freedesktop.org/) by Collabora
- [Stardust XR](https://stardustxr.org/) by Nova
- [VRto3D](https://github.com/oneup03/VRto3D) by oneup03
- [AITrack](https://github.com/AIRLegend/aitrack) by AIRLegend
- [OpenTrack](https://github.com/opentrack/opentrack)
- [ReShade](https://reshade.me/) + [SuperDepth3D](https://github.com/BlueSkyDefender/Depth3D)

## License

MIT License - See individual component licenses for their respective terms.
