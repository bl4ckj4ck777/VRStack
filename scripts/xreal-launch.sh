#!/bin/bash
#
# XREAL VR Stack Unified Launcher
# Launch different AR/VR modes with a single command
#

set -e

SCRIPT_DIR="$(dirname "$(readlink -f "$0")")"
CONFIG_DIR="$HOME/.config/VRStack"
CACHE_DIR="$HOME/.cache/VRStack"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

# Default values
GLASSES_DISPLAY="DP-9"
PRIMARY_DISPLAY="eDP-1"

# Load config if exists
if [[ -f "$CONFIG_DIR/displays.conf" ]]; then
    source "$CONFIG_DIR/displays.conf"
fi

usage() {
    cat << EOF
${CYAN}XREAL VR Stack Launcher${NC}

Usage: $(basename "$0") <mode> [options]

Modes:
  ${GREEN}desktop${NC}       - Standard AR desktop (Breezy Desktop virtual screen)
  ${GREEN}sbs${NC}           - Side-by-side 3D mode for 3D content/games
  ${GREEN}vr${NC}            - VR mode with Monado (for OpenXR games)
  ${GREEN}stardust${NC}      - 3D floating window desktop (Stardust XR)
  ${GREEN}game${NC} <name>   - Launch a game with optimal settings
  ${GREEN}reset${NC}         - Reset to normal desktop mode
  ${GREEN}status${NC}        - Show current mode and hardware status

Options:
  -d, --display <name>    Override glasses display name (default: $GLASSES_DISPLAY)
  -p, --primary <name>    Override primary display name (default: $PRIMARY_DISPLAY)
  -h, --help              Show this help message

Examples:
  $(basename "$0") desktop          # Start AR virtual desktop
  $(basename "$0") sbs              # Enable SBS 3D mode
  $(basename "$0") vr               # Start VR with Monado
  $(basename "$0") game portal      # Launch Portal with Depth3D

EOF
    exit 0
}

log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Check if glasses are connected
check_glasses() {
    if ! lsusb | grep -qi "3318"; then
        log_warn "XREAL glasses not detected via USB"
        return 1
    fi
    return 0
}

# Check if XRLinuxDriver is running
check_driver() {
    if ! pgrep -f "xr_driver" > /dev/null 2>&1; then
        log_info "Starting XRLinuxDriver..."
        xr_driver_cli -e 2>/dev/null || true
        sleep 1
    fi
}

# Get current display configuration
detect_displays() {
    # Try to auto-detect glasses display
    local glasses=$(xrandr --listmonitors 2>/dev/null | grep -i "xreal\|nreal\|air\|MRG" | awk '{print $NF}')
    if [[ -n "$glasses" ]]; then
        GLASSES_DISPLAY="$glasses"
    fi
    
    # Auto-detect primary (usually eDP for laptops)
    local primary=$(xrandr --listmonitors 2>/dev/null | grep "eDP" | awk '{print $NF}')
    if [[ -n "$primary" ]]; then
        PRIMARY_DISPLAY="$primary"
    fi
}

# Mode: Standard AR Desktop (Breezy)
mode_desktop() {
    log_info "Enabling AR Desktop mode (Breezy)..."
    
    check_driver
    
    # Enable Breezy Desktop mode
    xr_driver_cli -e 2>/dev/null || true
    xr_driver_cli -bd 2>/dev/null || true
    xr_driver_cli -sbs3d false 2>/dev/null || true
    
    log_info "AR Desktop mode active"
    log_info "Tap glasses twice to recenter, three times to recalibrate"
}

# Mode: SBS 3D
mode_sbs() {
    log_info "Enabling SBS 3D mode..."
    
    check_driver
    detect_displays
    
    # Disable Breezy XR effect first
    xr_driver_cli -d 2>/dev/null || true
    sleep 0.5
    
    # Enable driver and SBS
    xr_driver_cli -e 2>/dev/null || true
    xr_driver_cli -sbs3d true 2>/dev/null || true
    
    # Configure displays for SBS
    log_info "Configuring displays..."
    log_info "  Primary: $PRIMARY_DISPLAY (disabling)"
    log_info "  Glasses: $GLASSES_DISPLAY (3840x1080)"
    
    # Try gnome-randr first, fall back to xrandr
    if command -v gnome-randr &> /dev/null; then
        gnome-randr modify "$PRIMARY_DISPLAY" --off 2>/dev/null || true
        gnome-randr modify "$GLASSES_DISPLAY" --mode 3840x1080 --scale 1 2>/dev/null || true
    else
        # For X11/xrandr
        xrandr --output "$PRIMARY_DISPLAY" --off 2>/dev/null || true
        xrandr --output "$GLASSES_DISPLAY" --mode 3840x1080 --scale 1x1 2>/dev/null || true
    fi
    
    log_info "SBS mode active"
    log_info "Hold brightness+ on glasses for 3 seconds to enable hardware SBS"
    log_info "Run '$(basename "$0") reset' to return to normal"
}

# Mode: VR with Monado
mode_vr() {
    log_info "Starting VR mode with Monado..."
    
    # Check if Monado is installed
    if ! command -v monado-service &> /dev/null; then
        log_error "Monado not installed. Run the installer with monado component."
        exit 1
    fi
    
    # Set up OpenXR runtime
    mkdir -p "$HOME/.config/openxr/1"
    cat > "$HOME/.config/openxr/1/active_runtime.json" << 'EOF'
{
    "file_format_version": "1.0.0",
    "runtime": {
        "library_path": "libmonado.so"
    }
}
EOF
    
    # Configure Monado for XREAL
    export XRT_COMPOSITOR_FORCE_WAYLAND=1
    export XRT_COMPOSITOR_SCALE_PERCENTAGE=100
    
    # Start Monado service
    log_info "Starting Monado service..."
    monado-service &
    MONADO_PID=$!
    
    log_info "VR mode active (Monado PID: $MONADO_PID)"
    log_info "OpenXR applications should now detect the headset"
    log_info "Press Ctrl+C to stop Monado"
    
    # Wait for Monado to exit
    wait $MONADO_PID
}

# Mode: Stardust XR
mode_stardust() {
    log_info "Starting Stardust XR..."
    
    if ! command -v stardust-xr-server &> /dev/null; then
        log_error "Stardust XR not installed. Run the installer with stardust-xr component."
        exit 1
    fi
    
    # Start Stardust
    log_info "Launching Stardust XR server..."
    stardust-xr-server &
    sleep 2
    
    # Start flatland for 2D app support
    if command -v stardust-xr-flatland &> /dev/null; then
        log_info "Starting Flatland (2D app support)..."
        stardust-xr-flatland &
    fi
    
    # Start app launcher
    if command -v stardust-xr-protostar &> /dev/null; then
        log_info "Starting Hexagon Launcher..."
        stardust-xr-protostar &
    fi
    
    log_info "Stardust XR running"
    log_info "Use VR controllers or keyboard to interact"
    
    wait
}

# Mode: Launch game
mode_game() {
    local game_name="$1"
    
    if [[ -z "$game_name" ]]; then
        log_error "Please specify a game name"
        echo "Usage: $(basename "$0") game <game_name>"
        exit 1
    fi
    
    log_info "Launching game: $game_name"
    
    # Enable SBS mode first
    mode_sbs
    
    # Find game in Steam library
    local steam_apps="$HOME/.local/share/Steam/steamapps"
    local game_dir=$(find "$steam_apps/common" -maxdepth 1 -iname "*$game_name*" -type d 2>/dev/null | head -1)
    
    if [[ -z "$game_dir" ]]; then
        log_warn "Game not found in Steam library, launching Steam..."
        steam steam://run/"$game_name" &
    else
        log_info "Found game at: $game_dir"
        steam steam://run/"$game_name" &
    fi
    
    log_info "Game launching..."
    log_info "Press Home key to open ReShade overlay (if installed)"
}

# Mode: Reset to normal
mode_reset() {
    log_info "Resetting to normal desktop mode..."
    
    detect_displays
    
    # Disable SBS
    xr_driver_cli -sbs3d false 2>/dev/null || true
    
    # Re-enable both displays
    if command -v gnome-randr &> /dev/null; then
        gnome-randr modify "$PRIMARY_DISPLAY" --on --mode 1920x1080 --scale 1 2>/dev/null || true
        gnome-randr modify "$GLASSES_DISPLAY" --mode 1920x1080 --scale 1 2>/dev/null || true
    else
        xrandr --output "$PRIMARY_DISPLAY" --auto 2>/dev/null || true
        xrandr --output "$GLASSES_DISPLAY" --mode 1920x1080 --scale 1x1 2>/dev/null || true
    fi
    
    # Re-enable Breezy Desktop
    xr_driver_cli -e 2>/dev/null || true
    xr_driver_cli -bd 2>/dev/null || true
    
    log_info "Normal desktop mode restored"
}

# Mode: Status
mode_status() {
    echo -e "${CYAN}XREAL VR Stack Status${NC}"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo
    
    # Hardware
    echo -e "${GREEN}Hardware:${NC}"
    if check_glasses 2>/dev/null; then
        local glasses_info=$(lsusb | grep -i "3318" | head -1)
        echo "  ✓ Glasses: Connected ($glasses_info)"
    else
        echo "  ○ Glasses: Not detected"
    fi
    
    if ls /dev/video* &>/dev/null; then
        echo "  ✓ Webcam: Available"
    else
        echo "  ○ Webcam: Not detected"
    fi
    echo
    
    # Driver status
    echo -e "${GREEN}Driver Status:${NC}"
    if pgrep -f "xr_driver" > /dev/null 2>&1; then
        echo "  ✓ XRLinuxDriver: Running"
    else
        echo "  ○ XRLinuxDriver: Not running"
    fi
    
    if pgrep -f "monado" > /dev/null 2>&1; then
        echo "  ✓ Monado: Running"
    else
        echo "  ○ Monado: Not running"
    fi
    
    if pgrep -f "stardust" > /dev/null 2>&1; then
        echo "  ✓ Stardust XR: Running"
    else
        echo "  ○ Stardust XR: Not running"
    fi
    echo
    
    # Display configuration
    echo -e "${GREEN}Displays:${NC}"
    xrandr --listmonitors 2>/dev/null | tail -n +2 | while read line; do
        echo "  $line"
    done
    echo
    
    # SBS status
    echo -e "${GREEN}Current Mode:${NC}"
    if xr_driver_cli -g 2>/dev/null | grep -q "sbs3d.*true"; then
        echo "  SBS 3D: Enabled"
    else
        echo "  SBS 3D: Disabled"
    fi
}

# Parse arguments
MODE=""
while [[ $# -gt 0 ]]; do
    case $1 in
        -d|--display)
            GLASSES_DISPLAY="$2"
            shift 2
            ;;
        -p|--primary)
            PRIMARY_DISPLAY="$2"
            shift 2
            ;;
        -h|--help)
            usage
            ;;
        desktop|sbs|vr|stardust|game|reset|status)
            MODE="$1"
            shift
            break
            ;;
        *)
            log_error "Unknown option: $1"
            usage
            ;;
    esac
done

# Execute mode
case $MODE in
    desktop)
        mode_desktop
        ;;
    sbs)
        mode_sbs
        ;;
    vr)
        mode_vr
        ;;
    stardust)
        mode_stardust
        ;;
    game)
        mode_game "$1"
        ;;
    reset)
        mode_reset
        ;;
    status)
        mode_status
        ;;
    *)
        usage
        ;;
esac

