#!/bin/bash
#
# SBS Mode Toggle for XREAL Air 2 on GNOME Wayland
# Swaps monitor configs and toggles SBS mode
#

SCRIPT_DIR="$(dirname "$(readlink -f "$0")")"
CONFIG_DIR="$HOME/.config"
MONITORS_FILE="$CONFIG_DIR/monitors.xml"
NORMAL_CONFIG="$SCRIPT_DIR/monitors-normal.xml"
SBS_CONFIG="$SCRIPT_DIR/monitors-sbs.xml"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

usage() {
    echo "Usage: $0 [on|off|status]"
    echo "  on     - Enable SBS 3D mode (glasses only, 3840x1080)"
    echo "  off    - Disable SBS, restore normal dual-display"
    echo "  status - Show current mode"
    exit 1
}

check_configs() {
    if [[ ! -f "$NORMAL_CONFIG" ]]; then
        echo -e "${RED}Error: $NORMAL_CONFIG not found${NC}"
        echo "Please ensure monitors-normal.xml is in $SCRIPT_DIR"
        exit 1
    fi
    if [[ ! -f "$SBS_CONFIG" ]]; then
        echo -e "${RED}Error: $SBS_CONFIG not found${NC}"
        echo "Please ensure monitors-sbs.xml is in $SCRIPT_DIR"
        exit 1
    fi
}

reload_display_config() {
    echo -e "${YELLOW}Reloading display configuration...${NC}"
    
    # Method 1: Try dbus call to Mutter DisplayConfig
    gdbus call --session \
        --dest org.gnome.Mutter.DisplayConfig \
        --object-path /org/gnome/Mutter/DisplayConfig \
        --method org.gnome.Mutter.DisplayConfig.ApplyConfiguration 2>/dev/null
    
    # Method 2: Simulate monitor hotplug by toggling DPMS
    sleep 0.5
    
    # Method 3: If using X11 backend (shouldn't be, but just in case)
    if [[ "$XDG_SESSION_TYPE" == "x11" ]]; then
        xrandr --auto 2>/dev/null
    fi
    
    echo -e "${GREEN}Display config applied.${NC}"
    echo -e "${YELLOW}If display doesn't update, try: Settings > Displays > Apply${NC}"
}

enable_sbs() {
    echo -e "${GREEN}=== Enabling SBS 3D Mode ===${NC}"
    
    check_configs
    
    # Backup current config if not already backed up
    if [[ ! -f "$CONFIG_DIR/monitors.xml.backup" ]]; then
        cp "$MONITORS_FILE" "$CONFIG_DIR/monitors.xml.backup"
        echo "Backed up current config to monitors.xml.backup"
    fi
    
    # Disable XR effect first
    echo "Disabling Breezy Desktop XR effect..."
    xr_driver_cli -d 2>/dev/null
    sleep 0.3
    
    # Copy SBS config
    echo "Applying SBS display configuration..."
    cp "$SBS_CONFIG" "$MONITORS_FILE"
    
    # Reload display config
    reload_display_config
    
    # Enable driver and SBS mode
    echo "Enabling SBS in driver..."
    xr_driver_cli -e 2>/dev/null
    sleep 0.2
    xr_driver_cli -sbs3d true 2>/dev/null
    
    echo ""
    echo -e "${GREEN}=== SBS Mode Enabled ===${NC}"
    echo ""
    echo "IMPORTANT: Hold brightness+ button on glasses for 3 seconds"
    echo "           to activate hardware SBS mode (wait for beep)"
    echo ""
    echo "To return to normal: $0 off"
}

disable_sbs() {
    echo -e "${GREEN}=== Disabling SBS Mode ===${NC}"
    
    check_configs
    
    # Disable SBS in driver
    echo "Disabling SBS in driver..."
    xr_driver_cli -sbs3d false 2>/dev/null
    
    # Copy normal config
    echo "Applying normal display configuration..."
    cp "$NORMAL_CONFIG" "$MONITORS_FILE"
    
    # Reload display config
    reload_display_config
    
    # Re-enable Breezy Desktop mode
    echo "Re-enabling Breezy Desktop mode..."
    sleep 0.3
    xr_driver_cli -e 2>/dev/null
    xr_driver_cli -bd 2>/dev/null
    
    echo ""
    echo -e "${GREEN}=== Normal Mode Restored ===${NC}"
    echo ""
    echo "IMPORTANT: Hold brightness+ button on glasses for 3 seconds"
    echo "           to disable hardware SBS mode (wait for beep)"
    echo ""
    echo "You can now re-enable XR effect in Breezy Desktop app"
}

show_status() {
    echo "=== Current Status ==="
    echo ""
    echo "Driver status:"
    xr_driver_cli -s 2>/dev/null || echo "  Driver not responding"
    echo ""
    echo "SBS config in driver:"
    grep "sbs" ~/.config/xr_driver/config.ini 2>/dev/null
    echo ""
    echo "Current monitors:"
    xrandr --listmonitors 2>/dev/null
    echo ""
    echo "Resolution check:"
    xrandr 2>/dev/null | grep -A1 "DP-9\|nreal" | head -5
}

# Main
case "${1:-}" in
    on)
        enable_sbs
        ;;
    off)
        disable_sbs
        ;;
    status)
        show_status
        ;;
    *)
        usage
        ;;
esac
