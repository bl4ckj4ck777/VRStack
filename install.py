#!/usr/bin/env python3
"""
XREAL VR Stack Installer
A unified installer for Linux AR/VR components targeting XREAL and similar glasses.

Usage:
    ./install.py              # Interactive TUI mode
    ./install.py --minimal    # Just XRLinuxDriver + Breezy
    ./install.py --full       # Everything including optional components
    ./install.py --list       # Show available components
    ./install.py --uninstall  # Remove installed components
"""

import os
import sys
import subprocess
import shutil
import json
import argparse
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional, Callable
from enum import Enum, auto

# ============================================================================
# Configuration
# ============================================================================

INSTALL_DIR = Path.home() / ".local" / "share" / "VRStack"
BIN_DIR = Path.home() / ".local" / "bin"
CONFIG_DIR = Path.home() / ".config" / "VRStack"
CACHE_DIR = Path.home() / ".cache" / "VRStack"

class Distro(Enum):
    UBUNTU = auto()
    DEBIAN = auto()
    FEDORA = auto()
    ARCH = auto()
    OPENSUSE = auto()
    UNKNOWN = auto()

class ComponentStatus(Enum):
    NOT_INSTALLED = auto()
    INSTALLED = auto()
    UPDATE_AVAILABLE = auto()
    FAILED = auto()

# ============================================================================
# Utility Functions
# ============================================================================

def run(cmd: str | list, check: bool = True, capture: bool = False, 
        env: dict = None, cwd: str = None) -> subprocess.CompletedProcess:
    """Run a shell command with sensible defaults."""
    if isinstance(cmd, str):
        cmd = cmd.split()
    
    merged_env = {**os.environ, **(env or {})}
    
    return subprocess.run(
        cmd,
        check=check,
        capture_output=capture,
        text=True,
        env=merged_env,
        cwd=cwd
    )

def cmd_exists(cmd: str) -> bool:
    """Check if a command exists in PATH."""
    return shutil.which(cmd) is not None

def detect_distro() -> Distro:
    """Detect the Linux distribution."""
    if Path("/etc/os-release").exists():
        with open("/etc/os-release") as f:
            content = f.read().lower()
            if "ubuntu" in content:
                return Distro.UBUNTU
            elif "debian" in content:
                return Distro.DEBIAN
            elif "fedora" in content:
                return Distro.FEDORA
            elif "arch" in content:
                return Distro.ARCH
            elif "opensuse" in content:
                return Distro.OPENSUSE
    return Distro.UNKNOWN

def get_package_manager(distro: Distro) -> tuple[str, str, str]:
    """Return (install_cmd, update_cmd, search_cmd) for distro."""
    managers = {
        Distro.UBUNTU: ("sudo apt install -y", "sudo apt update", "apt search"),
        Distro.DEBIAN: ("sudo apt install -y", "sudo apt update", "apt search"),
        Distro.FEDORA: ("sudo dnf install -y", "sudo dnf check-update", "dnf search"),
        Distro.ARCH: ("sudo pacman -S --noconfirm", "sudo pacman -Sy", "pacman -Ss"),
        Distro.OPENSUSE: ("sudo zypper install -y", "sudo zypper refresh", "zypper search"),
    }
    return managers.get(distro, ("", "", ""))

def install_packages(packages: list[str], distro: Distro) -> bool:
    """Install system packages for the detected distro."""
    install_cmd, _, _ = get_package_manager(distro)
    if not install_cmd:
        print(f"[!] Unknown distro, please install manually: {' '.join(packages)}")
        return False
    
    try:
        run(f"{install_cmd} {' '.join(packages)}")
        return True
    except subprocess.CalledProcessError:
        return False

def clone_or_update(repo_url: str, dest: Path, branch: str = None) -> bool:
    """Clone a git repo or update if it exists."""
    if dest.exists():
        print(f"    Updating {dest.name}...")
        try:
            run("git pull", cwd=str(dest))
            return True
        except subprocess.CalledProcessError:
            return False
    else:
        print(f"    Cloning {dest.name}...")
        cmd = f"git clone {repo_url} {dest}"
        if branch:
            cmd = f"git clone -b {branch} {repo_url} {dest}"
        try:
            run(cmd)
            return True
        except subprocess.CalledProcessError:
            return False

# ============================================================================
# Hardware Detection
# ============================================================================

@dataclass
class HardwareInfo:
    glasses_detected: bool = False
    glasses_name: str = ""
    glasses_vendor_id: str = ""
    glasses_product_id: str = ""
    webcam_detected: bool = False
    webcam_name: str = ""
    webcam_path: str = ""
    gpu_vendor: str = ""
    gpu_name: str = ""

def detect_hardware() -> HardwareInfo:
    """Detect connected AR glasses, webcams, and GPU."""
    info = HardwareInfo()
    
    # Detect AR glasses via USB
    known_glasses = {
        ("3318", "0424"): "XREAL Air",
        ("3318", "0428"): "XREAL Air 2",
        ("3318", "0432"): "XREAL Air 2 Pro",
        ("3318", "0436"): "XREAL Air 2 Ultra",
        ("04d2", "1a60"): "Rokid Max",
        ("35ca", "0102"): "Viture One",
    }
    
    try:
        result = run("lsusb", capture=True)
        for line in result.stdout.splitlines():
            for (vid, pid), name in known_glasses.items():
                if f"{vid}:{pid}" in line.lower():
                    info.glasses_detected = True
                    info.glasses_name = name
                    info.glasses_vendor_id = vid
                    info.glasses_product_id = pid
                    break
    except Exception:
        pass
    
    # Detect webcam
    try:
        for i in range(10):
            dev = Path(f"/dev/video{i}")
            if dev.exists():
                result = run(f"v4l2-ctl -d {dev} --info", capture=True, check=False)
                if result.returncode == 0 and "Camera" in result.stdout:
                    info.webcam_detected = True
                    info.webcam_path = str(dev)
                    # Extract name
                    for line in result.stdout.splitlines():
                        if "Card type" in line:
                            info.webcam_name = line.split(":")[-1].strip()
                            break
                    break
    except Exception:
        pass
    
    # Detect GPU
    try:
        result = run("lspci", capture=True)
        for line in result.stdout.splitlines():
            if "VGA" in line or "3D" in line:
                line_lower = line.lower()
                if "nvidia" in line_lower:
                    info.gpu_vendor = "nvidia"
                elif "amd" in line_lower or "radeon" in line_lower:
                    info.gpu_vendor = "amd"
                elif "intel" in line_lower:
                    info.gpu_vendor = "intel"
                info.gpu_name = line.split(":")[-1].strip()
                break
    except Exception:
        pass
    
    return info

# ============================================================================
# Component System
# ============================================================================

@dataclass
class Component:
    """Base class for installable components."""
    name: str
    description: str
    category: str  # core, tracking, desktop, gaming, controllers
    required: bool = False
    dependencies: list[str] = field(default_factory=list)
    conflicts: list[str] = field(default_factory=list)
    
    def check_installed(self) -> ComponentStatus:
        """Check if this component is installed."""
        raise NotImplementedError
    
    def install(self, distro: Distro, hardware: HardwareInfo) -> bool:
        """Install this component."""
        raise NotImplementedError
    
    def uninstall(self) -> bool:
        """Uninstall this component."""
        raise NotImplementedError
    
    def configure(self, hardware: HardwareInfo) -> bool:
        """Configure this component for the detected hardware."""
        return True

# ============================================================================
# Component Implementations
# ============================================================================

class XRLinuxDriverComponent(Component):
    """XRLinuxDriver - Core driver for AR glasses IMU."""
    
    def __init__(self):
        super().__init__(
            name="xrlinuxdriver",
            description="Core driver for AR glasses (IMU, display detection)",
            category="core",
            required=True,
            dependencies=[],
        )
    
    def check_installed(self) -> ComponentStatus:
        if cmd_exists("xr_driver_cli"):
            return ComponentStatus.INSTALLED
        return ComponentStatus.NOT_INSTALLED
    
    def install(self, distro: Distro, hardware: HardwareInfo) -> bool:
        print(f"[*] Installing {self.name}...")
        
        # Install via the official script
        try:
            run("bash -c 'curl -Lo /tmp/xr_driver_setup.sh https://github.com/wheaney/XRLinuxDriver/releases/latest/download/xr_driver_setup.sh && chmod +x /tmp/xr_driver_setup.sh && /tmp/xr_driver_setup.sh'", check=True)
            return True
        except subprocess.CalledProcessError as e:
            print(f"[!] Failed to install XRLinuxDriver: {e}")
            return False
    
    def uninstall(self) -> bool:
        # XRLinuxDriver doesn't have a clean uninstall, but we can try
        paths = [
            Path.home() / ".local" / "bin" / "xr_driver_cli",
            Path.home() / ".local" / "share" / "xr_driver",
            Path.home() / ".config" / "xr_driver",
        ]
        for p in paths:
            if p.exists():
                if p.is_dir():
                    shutil.rmtree(p)
                else:
                    p.unlink()
        return True


class BreezyDesktopComponent(Component):
    """Breezy Desktop - Virtual desktop for AR glasses."""
    
    def __init__(self):
        super().__init__(
            name="breezy-desktop",
            description="Virtual desktop environment for AR glasses",
            category="core",
            required=True,
            dependencies=["xrlinuxdriver"],
        )
    
    def check_installed(self) -> ComponentStatus:
        # Breezy is bundled with XRLinuxDriver now
        config = Path.home() / ".config" / "xr_driver" / "config.ini"
        if config.exists():
            return ComponentStatus.INSTALLED
        return ComponentStatus.NOT_INSTALLED
    
    def install(self, distro: Distro, hardware: HardwareInfo) -> bool:
        # Breezy comes with XRLinuxDriver
        print(f"[*] {self.name} is bundled with XRLinuxDriver")
        return True
    
    def uninstall(self) -> bool:
        return True  # Handled by XRLinuxDriver


class MonadoComponent(Component):
    """Monado - Open source OpenXR runtime."""
    
    def __init__(self):
        super().__init__(
            name="monado",
            description="Open source OpenXR runtime (required for VR games)",
            category="core",
            dependencies=["xrlinuxdriver"],
        )
    
    def check_installed(self) -> ComponentStatus:
        if cmd_exists("monado-service"):
            return ComponentStatus.INSTALLED
        return ComponentStatus.NOT_INSTALLED
    
    def install(self, distro: Distro, hardware: HardwareInfo) -> bool:
        print(f"[*] Installing {self.name}...")
        
        if distro in [Distro.UBUNTU, Distro.DEBIAN]:
            # Try Monado PPA first
            try:
                run("sudo add-apt-repository -y ppa:monado-xr/monado")
                run("sudo apt update")
                run("sudo apt install -y libopenxr-loader1 libopenxr-dev monado")
                return True
            except subprocess.CalledProcessError:
                print("    PPA failed, building from source...")
                return self._build_from_source(distro)
        
        # Distro-specific installation
        packages = {
            Distro.UBUNTU: ["monado", "monado-cli"],
            Distro.DEBIAN: ["monado", "monado-cli"],
            Distro.FEDORA: ["monado"],
            Distro.ARCH: ["monado"],
        }
        
        distro_packages = packages.get(distro, [])
        if distro_packages:
            # Try package manager first
            if install_packages(distro_packages, distro):
                return True
        
        # Fall back to building from source
        print("    Package not available, building from source...")
        return self._build_from_source(distro)
    
    def _build_from_source(self, distro: Distro) -> bool:
        # Install build dependencies
        deps = {
            Distro.UBUNTU: [
                "build-essential", "cmake", "libeigen3-dev", "libgl-dev",
                "libvulkan-dev", "libx11-xcb-dev", "libxrandr-dev", "libxcb-randr0-dev",
                "libudev-dev", "libhidapi-dev", "libwayland-dev", "glslang-tools",
                "libcjson-dev", "libegl-dev", "libusb-1.0-0-dev"
            ],
            Distro.FEDORA: [
                "cmake", "gcc-c++", "eigen3-devel", "mesa-libGL-devel",
                "vulkan-headers", "libX11-devel", "libXrandr-devel",
                "systemd-devel", "hidapi-devel", "wayland-devel", "glslang",
                "cjson-devel", "mesa-libEGL-devel", "libusb1-devel"
            ],
        }
        
        distro_deps = deps.get(distro, [])
        if distro_deps:
            install_packages(distro_deps, distro)
        
        # Clone and build
        src_dir = CACHE_DIR / "monado"
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        
        if not clone_or_update("https://gitlab.freedesktop.org/monado/monado.git", src_dir):
            return False
        
        build_dir = src_dir / "build"
        build_dir.mkdir(exist_ok=True)
        
        try:
            run("cmake .. -DCMAKE_INSTALL_PREFIX=$HOME/.local", cwd=str(build_dir))
            run("make -j$(nproc)", cwd=str(build_dir))
            run("make install", cwd=str(build_dir))
            return True
        except subprocess.CalledProcessError as e:
            print(f"[!] Build failed: {e}")
            return False
    
    def uninstall(self) -> bool:
        # Remove local installation
        for binary in ["monado-service", "monado-cli"]:
            path = BIN_DIR / binary
            if path.exists():
                path.unlink()
        return True


class AITrackComponent(Component):
    """AITrack - Neural network head tracking via webcam."""
    
    def __init__(self):
        super().__init__(
            name="aitrack",
            description="Webcam-based head tracking using neural networks (6DOF)",
            category="tracking",
            dependencies=[],
        )
    
    def check_installed(self) -> ComponentStatus:
        aitrack_dir = INSTALL_DIR / "aitrack"
        if aitrack_dir.exists() and (aitrack_dir / "AITrack").exists():
            return ComponentStatus.INSTALLED
        return ComponentStatus.NOT_INSTALLED
    
    def install(self, distro: Distro, hardware: HardwareInfo) -> bool:
        print(f"[*] Installing {self.name}...")
        
        # AITrack needs to be built from source on Linux
        deps = {
            Distro.UBUNTU: ["libopencv-dev", "libonnxruntime-dev", "qt5-default", "cmake", "build-essential"],
            Distro.FEDORA: ["opencv-devel", "onnxruntime-devel", "qt5-qtbase-devel", "cmake", "gcc-c++"],
            Distro.ARCH: ["opencv", "onnxruntime", "qt5-base", "cmake", "base-devel"],
        }
        
        distro_deps = deps.get(distro, [])
        if distro_deps:
            install_packages(distro_deps, distro)
        
        src_dir = CACHE_DIR / "aitrack"
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        
        if not clone_or_update("https://github.com/AIRLegend/aitrack.git", src_dir):
            return False
        
        # Build
        client_dir = src_dir / "Client"
        build_dir = client_dir / "build"
        build_dir.mkdir(exist_ok=True)
        
        try:
            run("cmake ..", cwd=str(build_dir))
            run("make -j$(nproc)", cwd=str(build_dir))
            
            # Install to our directory
            INSTALL_DIR.mkdir(parents=True, exist_ok=True)
            install_path = INSTALL_DIR / "aitrack"
            install_path.mkdir(exist_ok=True)
            shutil.copy(build_dir / "AITrack", install_path / "AITrack")
            
            # Create launcher script
            launcher = BIN_DIR / "aitrack"
            launcher.write_text(f"""#!/bin/bash
exec {install_path}/AITrack "$@"
""")
            launcher.chmod(0o755)
            
            return True
        except subprocess.CalledProcessError as e:
            print(f"[!] Build failed: {e}")
            return False
    
    def uninstall(self) -> bool:
        shutil.rmtree(INSTALL_DIR / "aitrack", ignore_errors=True)
        (BIN_DIR / "aitrack").unlink(missing_ok=True)
        return True


class OpenTrackComponent(Component):
    """OpenTrack - Head tracking software with multiple input sources."""
    
    def __init__(self):
        super().__init__(
            name="opentrack",
            description="Head tracking hub (combines multiple tracking sources)",
            category="tracking",
            dependencies=[],
        )
    
    def check_installed(self) -> ComponentStatus:
        if cmd_exists("opentrack"):
            return ComponentStatus.INSTALLED
        return ComponentStatus.NOT_INSTALLED
    
    def install(self, distro: Distro, hardware: HardwareInfo) -> bool:
        print(f"[*] Installing {self.name}...")
        
        if distro in [Distro.UBUNTU, Distro.DEBIAN]:
            # Use PPA for Ubuntu/Debian
            try:
                run("sudo add-apt-repository -y ppa:opentrack-maintainers/opentrack")
                run("sudo apt update")
                run("sudo apt install -y opentrack")
                return True
            except subprocess.CalledProcessError:
                print("    PPA failed, trying AppImage...")
                return self._install_appimage()
        
        elif distro == Distro.ARCH:
            # AUR package
            try:
                run("yay -S --noconfirm opentrack")
                return True
            except subprocess.CalledProcessError:
                return self._install_appimage()
        
        return self._install_appimage()
    
    def _install_appimage(self) -> bool:
        """Download and install AppImage as fallback."""
        try:
            # Get latest release URL
            appimage_url = "https://github.com/opentrack/opentrack/releases/latest/download/opentrack-linux-x86_64.AppImage"
            dest = BIN_DIR / "opentrack"
            BIN_DIR.mkdir(parents=True, exist_ok=True)
            
            run(f"curl -L -o {dest} {appimage_url}")
            dest.chmod(0o755)
            return True
        except subprocess.CalledProcessError as e:
            print(f"[!] AppImage download failed: {e}")
            return False
    
    def uninstall(self) -> bool:
        (BIN_DIR / "opentrack").unlink(missing_ok=True)
        return True

class StardustXRComponent(Component):
    """Stardust XR - 3D desktop environment."""
    
    def __init__(self):
        super().__init__(
            name="stardust-xr",
            description="3D desktop with floating windows, skyboxes, and XR widgets",
            category="desktop",
            dependencies=["monado"],
        )
    
    def check_installed(self) -> ComponentStatus:
        if cmd_exists("stardust-xr-server"):
            return ComponentStatus.INSTALLED
        return ComponentStatus.NOT_INSTALLED
    
    def install(self, distro: Distro, hardware: HardwareInfo) -> bool:
        print(f"[*] Installing {self.name}...")
        
        # Fedora has Stardust in Terra repos
        if distro == Distro.FEDORA:
            try:
                # Add Terra repo if not present
                run("sudo dnf install -y --nogpgcheck --repofrompath 'terra,https://repos.fyralabs.com/terra$releasever' terra-release", check=False)
                run("sudo dnf install -y stardust-xr-server stardust-xr-flatland stardust-xr-protostar stardust-xr-atmosphere")
                return True
            except subprocess.CalledProcessError:
                pass
        
        # Build from source for other distros
        return self._build_from_source(distro)
    
    def _build_from_source(self, distro: Distro) -> bool:
        # Install Rust if needed
        if not cmd_exists("cargo"):
            print("    Installing Rust...")
            run("curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y")
        
        repos = [
            ("https://github.com/StardustXR/server.git", "stardust-server"),
            ("https://github.com/StardustXR/flatland.git", "stardust-flatland"),
            ("https://github.com/StardustXR/protostar.git", "stardust-protostar"),
        ]
        
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        
        for repo_url, name in repos:
            src_dir = CACHE_DIR / name
            if not clone_or_update(repo_url, src_dir):
                return False
            
            try:
                run("cargo build --release", cwd=str(src_dir))
                # Install binary
                binary_name = name.replace("stardust-", "stardust-xr-")
                target = src_dir / "target" / "release" / binary_name
                if target.exists():
                    BIN_DIR.mkdir(parents=True, exist_ok=True)
                    shutil.copy(target, BIN_DIR / binary_name)
            except subprocess.CalledProcessError as e:
                print(f"[!] Failed to build {name}: {e}")
                return False
        
        return True
    
    def uninstall(self) -> bool:
        for binary in ["stardust-xr-server", "stardust-xr-flatland", "stardust-xr-protostar"]:
            (BIN_DIR / binary).unlink(missing_ok=True)
        return True


class VRto3DComponent(Component):
    """VRto3D - Play VR games with AR glasses using SBS output."""
    
    def __init__(self):
        super().__init__(
            name="vrto3d",
            description="OpenVR driver for SBS 3D output (play VR games on AR glasses)",
            category="gaming",
            dependencies=["xrlinuxdriver"],
        )
    
    def check_installed(self) -> ComponentStatus:
        vrto3d_dir = Path.home() / ".steam" / "steam" / "steamapps" / "common" / "SteamVR" / "drivers" / "vrto3d"
        if vrto3d_dir.exists():
            return ComponentStatus.INSTALLED
        return ComponentStatus.NOT_INSTALLED
    
    def install(self, distro: Distro, hardware: HardwareInfo) -> bool:
        print(f"[*] Installing {self.name}...")
        
        src_dir = CACHE_DIR / "vrto3d"
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        
        if not clone_or_update("https://github.com/oneup03/VRto3D.git", src_dir):
            return False
        
        # Build
        try:
            run("cmake -B build", cwd=str(src_dir))
            run("cmake --build build --config Release", cwd=str(src_dir))
            
            # Install to SteamVR drivers directory
            steamvr_drivers = Path.home() / ".steam" / "steam" / "steamapps" / "common" / "SteamVR" / "drivers"
            if not steamvr_drivers.exists():
                print("[!] SteamVR not found. Please install SteamVR first.")
                return False
            
            vrto3d_dest = steamvr_drivers / "vrto3d"
            if vrto3d_dest.exists():
                shutil.rmtree(vrto3d_dest)
            shutil.copytree(src_dir / "build" / "vrto3d", vrto3d_dest)
            
            return True
        except subprocess.CalledProcessError as e:
            print(f"[!] Build failed: {e}")
            return False
    
    def uninstall(self) -> bool:
        vrto3d_dir = Path.home() / ".steam" / "steam" / "steamapps" / "common" / "SteamVR" / "drivers" / "vrto3d"
        if vrto3d_dir.exists():
            shutil.rmtree(vrto3d_dir)
        return True


class Depth3DComponent(Component):
    """ReShade + Depth3D - Convert 2D games to stereoscopic 3D."""
    
    def __init__(self):
        super().__init__(
            name="depth3d",
            description="ReShade + SuperDepth3D shader for 3D in regular games",
            category="gaming",
            dependencies=["xrlinuxdriver"],
        )
    
    def check_installed(self) -> ComponentStatus:
        reshade_script = INSTALL_DIR / "reshade-steam-proton"
        if reshade_script.exists():
            return ComponentStatus.INSTALLED
        return ComponentStatus.NOT_INSTALLED
    
    def install(self, distro: Distro, hardware: HardwareInfo) -> bool:
        print(f"[*] Installing {self.name}...")
        
        # Install dependencies
        deps = ["p7zip-full", "curl", "wget"]
        install_packages(deps, distro)
        
        src_dir = INSTALL_DIR / "reshade-steam-proton"
        INSTALL_DIR.mkdir(parents=True, exist_ok=True)
        
        if not clone_or_update("https://github.com/kevinlekiller/reshade-steam-proton.git", src_dir):
            return False
        
        # Make executable
        reshade_script = src_dir / "reshade-linux.sh"
        if reshade_script.exists():
            reshade_script.chmod(0o755)
        
        # Create launcher
        launcher = BIN_DIR / "reshade-setup"
        launcher.parent.mkdir(parents=True, exist_ok=True)
        launcher.write_text(f"""#!/bin/bash
cd "{src_dir}"
exec ./reshade-linux.sh "$@"
""")
        launcher.chmod(0o755)
        
        print("    Run 'reshade-setup' to install ReShade for specific games")
        return True
    
    def uninstall(self) -> bool:
        shutil.rmtree(INSTALL_DIR / "reshade-steam-proton", ignore_errors=True)
        (BIN_DIR / "reshade-setup").unlink(missing_ok=True)
        return True


# ============================================================================
# Component Registry
# ============================================================================

ALL_COMPONENTS: list[Component] = [
    XRLinuxDriverComponent(),
    BreezyDesktopComponent(),
    MonadoComponent(),
    AITrackComponent(),
    OpenTrackComponent(),
    StardustXRComponent(),
    VRto3DComponent(),
    Depth3DComponent(),
]

def get_component(name: str) -> Optional[Component]:
    """Get a component by name."""
    for c in ALL_COMPONENTS:
        if c.name == name:
            return c
    return None

def resolve_dependencies(selected: list[str]) -> list[str]:
    """Resolve dependencies and return ordered install list."""
    result = []
    visited = set()
    
    def visit(name: str):
        if name in visited:
            return
        visited.add(name)
        
        component = get_component(name)
        if component:
            for dep in component.dependencies:
                visit(dep)
            result.append(name)
    
    for name in selected:
        visit(name)
    
    return result

# ============================================================================
# TUI Interface
# ============================================================================

class Colors:
    RESET = "\033[0m"
    BOLD = "\033[1m"
    RED = "\033[31m"
    GREEN = "\033[32m"
    YELLOW = "\033[33m"
    BLUE = "\033[34m"
    MAGENTA = "\033[35m"
    CYAN = "\033[36m"

def clear_screen():
    os.system('clear' if os.name == 'posix' else 'cls')

def print_header():
    print(f"""
{Colors.CYAN}{Colors.BOLD}╔══════════════════════════════════════════════════════════════╗
║             XREAL VR Stack Installer v0.1.0                  ║
║         Unified Linux AR/VR Component Manager                ║
╚══════════════════════════════════════════════════════════════╝{Colors.RESET}
""")

def print_hardware_info(hardware: HardwareInfo):
    print(f"{Colors.BOLD}Detected Hardware:{Colors.RESET}")
    
    if hardware.glasses_detected:
        print(f"  {Colors.GREEN}✓{Colors.RESET} AR Glasses: {hardware.glasses_name}")
    else:
        print(f"  {Colors.YELLOW}○{Colors.RESET} AR Glasses: Not detected (will work when connected)")
    
    if hardware.webcam_detected:
        print(f"  {Colors.GREEN}✓{Colors.RESET} Webcam: {hardware.webcam_name} ({hardware.webcam_path})")
    else:
        print(f"  {Colors.YELLOW}○{Colors.RESET} Webcam: Not detected (needed for 6DOF tracking)")
    
    if hardware.gpu_vendor:
        print(f"  {Colors.GREEN}✓{Colors.RESET} GPU: {hardware.gpu_name} ({hardware.gpu_vendor})")
    
    print()

def print_component_list(hardware: HardwareInfo):
    print(f"{Colors.BOLD}Available Components:{Colors.RESET}\n")
    
    categories = {
        "core": "Core (Required)",
        "tracking": "Head Tracking",
        "desktop": "AR Desktop",
        "gaming": "Gaming",
        "controllers": "Controllers",
    }
    
    for cat_id, cat_name in categories.items():
        components = [c for c in ALL_COMPONENTS if c.category == cat_id]
        if not components:
            continue
        
        print(f"  {Colors.BOLD}{cat_name}:{Colors.RESET}")
        for c in components:
            status = c.check_installed()
            if status == ComponentStatus.INSTALLED:
                status_str = f"{Colors.GREEN}[installed]{Colors.RESET}"
            else:
                status_str = f"{Colors.YELLOW}[not installed]{Colors.RESET}"
            
            req_str = f"{Colors.RED}*{Colors.RESET}" if c.required else " "
            print(f"    {req_str} {c.name:20} {status_str:30} {c.description}")
        print()

def interactive_select(hardware: HardwareInfo) -> list[str]:
    """Interactive component selection."""
    selected = []
    
    # Always include required components
    for c in ALL_COMPONENTS:
        if c.required:
            selected.append(c.name)
    
    print(f"{Colors.BOLD}Select additional components to install:{Colors.RESET}")
    print("(Enter component names separated by spaces, or 'all' for everything)\n")
    
    optional = [c for c in ALL_COMPONENTS if not c.required]
    for i, c in enumerate(optional, 1):
        status = c.check_installed()
        status_str = f"{Colors.GREEN}✓{Colors.RESET}" if status == ComponentStatus.INSTALLED else " "
        print(f"  {status_str} {i}. {c.name:20} - {c.description}")
    
    print()
    choice = input(f"{Colors.CYAN}Selection (numbers or names, 'all', or Enter for core only): {Colors.RESET}").strip()
    
    if choice.lower() == 'all':
        selected = [c.name for c in ALL_COMPONENTS]
    elif choice:
        for item in choice.split():
            if item.isdigit():
                idx = int(item) - 1
                if 0 <= idx < len(optional):
                    selected.append(optional[idx].name)
            else:
                if get_component(item):
                    selected.append(item)
    
    return list(set(selected))

def run_installation(components: list[str], distro: Distro, hardware: HardwareInfo) -> bool:
    """Run the installation for selected components."""
    ordered = resolve_dependencies(components)
    
    print(f"\n{Colors.BOLD}Installation Plan:{Colors.RESET}")
    for name in ordered:
        c = get_component(name)
        status = c.check_installed()
        if status == ComponentStatus.INSTALLED:
            print(f"  {Colors.GREEN}✓{Colors.RESET} {name} (already installed)")
        else:
            print(f"  {Colors.YELLOW}○{Colors.RESET} {name} (will install)")
    
    print()
    confirm = input(f"{Colors.CYAN}Proceed with installation? [Y/n]: {Colors.RESET}").strip().lower()
    if confirm and confirm != 'y':
        print("Installation cancelled.")
        return False
    
    print()
    success = True
    for name in ordered:
        c = get_component(name)
        if c.check_installed() == ComponentStatus.INSTALLED:
            continue
        
        if not c.install(distro, hardware):
            print(f"{Colors.RED}[!] Failed to install {name}{Colors.RESET}")
            success = False
        else:
            print(f"{Colors.GREEN}[✓] Installed {name}{Colors.RESET}")
            c.configure(hardware)
    
    return success

# ============================================================================
# Main Entry Point
# ============================================================================

def main():
    parser = argparse.ArgumentParser(description="XREAL VR Stack Installer")
    parser.add_argument("--minimal", action="store_true", help="Install only core components")
    parser.add_argument("--full", action="store_true", help="Install all components")
    parser.add_argument("--list", action="store_true", help="List available components")
    parser.add_argument("--uninstall", action="store_true", help="Uninstall components")
    parser.add_argument("--components", nargs="+", help="Specific components to install")
    args = parser.parse_args()
    
    clear_screen()
    print_header()
    
    # Detect system
    distro = detect_distro()
    print(f"Detected distro: {Colors.CYAN}{distro.name}{Colors.RESET}\n")
    
    hardware = detect_hardware()
    print_hardware_info(hardware)
    
    if args.list:
        print_component_list(hardware)
        return
    
    if args.uninstall:
        print("Uninstalling all components...")
        for c in ALL_COMPONENTS:
            if c.check_installed() == ComponentStatus.INSTALLED:
                print(f"  Removing {c.name}...")
                c.uninstall()
        print("Done!")
        return
    
    # Determine what to install
    if args.minimal:
        selected = [c.name for c in ALL_COMPONENTS if c.required]
    elif args.full:
        selected = [c.name for c in ALL_COMPONENTS]
    elif args.components:
        selected = args.components
    else:
        print_component_list(hardware)
        selected = interactive_select(hardware)
    
    if not selected:
        print("No components selected.")
        return
    
    # Run installation
    if run_installation(selected, distro, hardware):
        print(f"\n{Colors.GREEN}{Colors.BOLD}Installation complete!{Colors.RESET}")
        print(f"\nNext steps:")
        print(f"  1. Connect your AR glasses")
        print(f"  2. Run 'xr_driver_cli -e' to enable the driver")
        print(f"  3. Check the wiki for per-component setup: https://github.com/wheaney/XRLinuxDriver")
    else:
        print(f"\n{Colors.YELLOW}Installation completed with some errors.{Colors.RESET}")
        print("Check the output above for details.")

if __name__ == "__main__":
    main()
