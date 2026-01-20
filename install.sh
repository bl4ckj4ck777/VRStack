#!/bin/bash
#
# XREAL VR Stack Quick Installer
# Run with: curl -sSL https://raw.githubusercontent.com/bl4ckj4ck777/VRStack/main/install.sh | bash
#

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

REPO_URL="https://github.com/bl4ckj4ck777/VRStack.git"
INSTALL_DIR="$HOME/.local/share/VRStack"
BIN_DIR="$HOME/.local/bin"

echo -e "${CYAN}"
cat << 'EOF'
╔══════════════════════════════════════════════════════════════╗
║             XREAL VR Stack Quick Installer                   ║
║         Unified Linux AR/VR Component Manager                ║
╚══════════════════════════════════════════════════════════════╝
EOF
echo -e "${NC}"

# Check dependencies
echo -e "${GREEN}Checking dependencies...${NC}"

check_command() {
    if ! command -v "$1" &> /dev/null; then
        echo -e "${RED}Missing: $1${NC}"
        return 1
    fi
    echo -e "  ${GREEN}✓${NC} $1"
    return 0
}

MISSING=0
check_command git || MISSING=1
check_command python3 || MISSING=1
check_command curl || MISSING=1

if [[ $MISSING -eq 1 ]]; then
    echo -e "\n${YELLOW}Installing missing dependencies...${NC}"
    
    if command -v apt &> /dev/null; then
        sudo apt update && sudo apt install -y git python3 curl
    elif command -v dnf &> /dev/null; then
        sudo dnf install -y git python3 curl
    elif command -v pacman &> /dev/null; then
        sudo pacman -S --noconfirm git python curl
    else
        echo -e "${RED}Please install git, python3, and curl manually${NC}"
        exit 1
    fi
fi

# Clone or update repository
echo -e "\n${GREEN}Setting up XREAL VR Stack...${NC}"

if [[ -d "$INSTALL_DIR" ]]; then
    echo "  Updating existing installation..."
    cd "$INSTALL_DIR"
    git pull
else
    echo "  Cloning repository..."
    git clone "$REPO_URL" "$INSTALL_DIR"
    cd "$INSTALL_DIR"
fi

# Make scripts executable
chmod +x install.py
chmod +x scripts/*.sh

# Create bin directory and symlinks
mkdir -p "$BIN_DIR"

# Link the launcher
ln -sf "$INSTALL_DIR/scripts/xreal-launch.sh" "$BIN_DIR/xreal-launch"

# Add to PATH if needed
if [[ ":$PATH:" != *":$BIN_DIR:"* ]]; then
    echo -e "\n${YELLOW}Adding $BIN_DIR to PATH...${NC}"
    
    SHELL_RC=""
    if [[ -f "$HOME/.bashrc" ]]; then
        SHELL_RC="$HOME/.bashrc"
    elif [[ -f "$HOME/.zshrc" ]]; then
        SHELL_RC="$HOME/.zshrc"
    fi
    
    if [[ -n "$SHELL_RC" ]]; then
        echo 'export PATH="$HOME/.local/bin:$PATH"' >> "$SHELL_RC"
        echo -e "  Added to $SHELL_RC"
        echo -e "  ${YELLOW}Run 'source $SHELL_RC' or restart your terminal${NC}"
    fi
fi

# Run the interactive installer
echo -e "\n${GREEN}Launching component installer...${NC}\n"
exec < /dev/tty  # Reattach stdin to terminal
python3 install.py

echo -e "\n${GREEN}Installation complete!${NC}"
echo -e "\nUsage:"
echo -e "  ${CYAN}xreal-launch desktop${NC}  - Start AR virtual desktop"
echo -e "  ${CYAN}xreal-launch sbs${NC}      - Enable SBS 3D mode"
echo -e "  ${CYAN}xreal-launch vr${NC}       - Start VR with Monado"
echo -e "  ${CYAN}xreal-launch status${NC}   - Check system status"
echo -e "  ${CYAN}xreal-launch --help${NC}   - Show all options"
