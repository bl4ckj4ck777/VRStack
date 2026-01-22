#!/usr/bin/env python3
"""
VRStack Installer
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
import multiprocessing
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
        env: dict = None, cwd: str = None, shell: bool = False) -> subprocess.CompletedProcess:
    """Run a shell command with sensible defaults.
    
    Args:
        cmd: Command to run (string or list)
        check: Raise exception on non-zero exit
        capture: Capture stdout/stderr
        env: Additional environment variables
        cwd: Working directory
        shell: Use shell execution (required for pipes, redirects, etc.)
    """
    merged_env = {**os.environ, **(env or {})}
    
    if shell:
        # For shell=True, cmd should be a string
        if isinstance(cmd, list):
            cmd = ' '.join(cmd)
        return subprocess.run(
            cmd,
            shell=True,
            check=check,
            capture_output=capture,
            text=True,
            env=merged_env,
            cwd=cwd
        )
    else:
        if isinstance(cmd, str):
            cmd = cmd.split()
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
        run(f"{install_cmd} {' '.join(packages)}", shell=True)
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
            run(cmd, shell=True)
            return True
        except subprocess.CalledProcessError:
            return False

def get_num_cores() -> int:
    """Get the number of CPU cores for parallel builds."""
    try:
        return multiprocessing.cpu_count()
    except Exception:
        return 4  # Safe default

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
            run("curl -Lo /tmp/xr_driver_setup.sh https://github.com/wheaney/XRLinuxDriver/releases/latest/download/xr_driver_setup.sh", shell=True)
            run("chmod +x /tmp/xr_driver_setup.sh", shell=True)
            run("/tmp/xr_driver_setup.sh", shell=True)
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
                print("    Trying Monado PPA...")
                run("sudo add-apt-repository -y ppa:monado-xr/monado", shell=True)
                run("sudo apt update", shell=True)
                run("sudo apt install -y libopenxr-loader1 libopenxr-dev monado", shell=True)
                return True
            except subprocess.CalledProcessError:
                print("    PPA failed, building from source...")
                return self._build_from_source(distro)
        
        elif distro == Distro.FEDORA:
            try:
                run("sudo dnf install -y monado", shell=True)
                return True
            except subprocess.CalledProcessError:
                return self._build_from_source(distro)
        
        elif distro == Distro.ARCH:
            try:
                run("sudo pacman -S --noconfirm monado", shell=True)
                return True
            except subprocess.CalledProcessError:
                return self._build_from_source(distro)
        
        return self._build_from_source(distro)
    
    def _build_from_source(self, distro: Distro) -> bool:
        """Build Monado from source."""
        # Install build dependencies
        deps = {
            Distro.UBUNTU: [
                "build-essential", "cmake", "libeigen3-dev", "libgl-dev",
                "libvulkan-dev", "libx11-xcb-dev", "libxrandr-dev", "libxcb-randr0-dev",
                "libudev-dev", "libhidapi-dev", "libwayland-dev", "glslang-tools",
                "libcjson-dev", "libegl-dev", "libusb-1.0-0-dev"
            ],
            Distro.DEBIAN: [
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
            run(f"cmake .. -DCMAKE_INSTALL_PREFIX={Path.home()}/.local", cwd=str(build_dir), shell=True)
            num_cores = get_num_cores()
            run(f"make -j{num_cores}", cwd=str(build_dir), shell=True)
            run("make install", cwd=str(build_dir), shell=True)
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


class OpenTrackComponent(Component):
    """OpenTrack - Head tracking software (includes NeuralNet face tracker)."""
    
    def __init__(self):
        super().__init__(
            name="opentrack",
            description="Head tracking with webcam AI (NeuralNet tracker built-in)",
            category="tracking",
            dependencies=[],
        )
    
    def check_installed(self) -> ComponentStatus:
        if cmd_exists("opentrack"):
            return ComponentStatus.INSTALLED
        return ComponentStatus.NOT_INSTALLED
    
    def install(self, distro: Distro, hardware: HardwareInfo) -> bool:
        print(f"[*] Installing {self.name}...")
        print("    Building from source (this may take a few minutes)...")
        
        # Install build dependencies
        deps = {
            Distro.UBUNTU: [
                "cmake", "git", "qttools5-dev", "qtbase5-private-dev",
                "libprocps-dev", "libopencv-dev", "libqt5x11extras5-dev",
                "qt6-base-dev", "qt6-tools-dev", "qt6-tools-dev-tools",
                "qt6-base-private-dev"
            ],
            Distro.DEBIAN: [
                "cmake", "git", "qttools5-dev", "qtbase5-private-dev",
                "libprocps-dev", "libopencv-dev", "libqt5x11extras5-dev",
                "qt6-base-dev", "qt6-tools-dev", "qt6-tools-dev-tools",
                "qt6-base-private-dev"
            ],
            Distro.FEDORA: [
                "cmake", "git", "qt6-qttools-devel", "qt6-qtbase-private-devel",
                "procps-ng-devel", "opencv-devel"
            ],
            Distro.ARCH: [
                "cmake", "git", "qt6-tools", "qt6-base", "opencv", "procps-ng"
            ],
        }
        
        distro_deps = deps.get(distro, [])
        if distro_deps:
            install_packages(distro_deps, distro)
        
        # Clone and build
        src_dir = CACHE_DIR / "opentrack-src"
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        
        if not clone_or_update("https://github.com/opentrack/opentrack.git", src_dir):
            return False
        
        build_dir = src_dir / "build"
        build_dir.mkdir(exist_ok=True)
        
        try:
            run(f"cmake .. -DCMAKE_INSTALL_PREFIX={Path.home()}/.local", cwd=str(build_dir), shell=True)
            num_cores = get_num_cores()
            run(f"make -j{num_cores}", cwd=str(build_dir), shell=True)
            run("make install", cwd=str(build_dir), shell=True)
            return True
        except subprocess.CalledProcessError as e:
            print(f"[!] Build failed: {e}")
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
                run("sudo dnf install -y --nogpgcheck --repofrompath 'terra,https://repos.fyralabs.com/terra$releasever' terra-release", shell=True, check=False)
                run("sudo dnf install -y stardust-xr-server stardust-xr-flatland stardust-xr-protostar stardust-xr-atmosphere", shell=True)
                return True
            except subprocess.CalledProcessError:
                pass
        
        # Build from source for other distros
        return self._build_from_source(distro)
    
    def _build_from_source(self, distro: Distro) -> bool:
        """Build Stardust XR from source."""
        # Install Rust if needed
        if not cmd_exists("cargo"):
            print("    Installing Rust...")
            try:
                run("curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y", shell=True)
                # Source cargo env for this session
                cargo_env = Path.home() / ".cargo" / "env"
                if cargo_env.exists():
                    os.environ["PATH"] = f"{Path.home()}/.cargo/bin:" + os.environ.get("PATH", "")
            except subprocess.CalledProcessError as e:
                print(f"[!] Failed to install Rust: {e}")
                return False
        
        # Install build dependencies (including libasound2-dev for ALSA)
        deps = {
            Distro.UBUNTU: ["libfontconfig1-dev", "libxkbcommon-dev", "pkg-config", "libasound2-dev"],
            Distro.DEBIAN: ["libfontconfig1-dev", "libxkbcommon-dev", "pkg-config", "libasound2-dev"],
            Distro.FEDORA: ["fontconfig-devel", "libxkbcommon-devel", "pkg-config", "alsa-lib-devel"],
            Distro.ARCH: ["fontconfig", "libxkbcommon", "pkgconf", "alsa-lib"],
        }
        
        distro_deps = deps.get(distro, [])
        if distro_deps:
            install_packages(distro_deps, distro)
        
        repos = [
            ("https://github.com/StardustXR/server.git", "stardust-server", "stardust-xr-server"),
            ("https://github.com/StardustXR/flatland.git", "stardust-flatland", "flatland"),
            ("https://github.com/StardustXR/protostar.git", "stardust-protostar", "hexagon_launcher"),
        ]
        
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        BIN_DIR.mkdir(parents=True, exist_ok=True)
        
        success = True
        for repo_url, dir_name, binary_name in repos:
            src_dir = CACHE_DIR / dir_name
            if not clone_or_update(repo_url, src_dir):
                success = False
                continue
            
            try:
                print(f"    Building {dir_name}...")
                # Ensure cargo is in PATH
                cargo_bin = Path.home() / ".cargo" / "bin" / "cargo"
                cargo_cmd = str(cargo_bin) if cargo_bin.exists() else "cargo"
                
                run(f"{cargo_cmd} build --release", cwd=str(src_dir), shell=True)
                
                # Find and install binary
                target_dir = src_dir / "target" / "release"
                
                # Try multiple possible binary names
                possible_names = [binary_name, dir_name.replace("-", "_"), dir_name, "stardust-xr-server"]
                
                installed = False
                for candidate in possible_names:
                    binary_path = target_dir / candidate
                    if binary_path.exists() and binary_path.is_file() and os.access(binary_path, os.X_OK):
                        # Determine destination name
                        if candidate == "stardust-xr-server":
                            dest_name = "stardust-xr-server"
                        elif candidate in ["flatland", "hexagon_launcher"]:
                            dest_name = f"stardust-xr-{candidate}"
                        else:
                            dest_name = candidate
                        
                        shutil.copy(binary_path, BIN_DIR / dest_name)
                        (BIN_DIR / dest_name).chmod(0o755)
                        print(f"    Installed {dest_name}")
                        installed = True
                        break
                
                if not installed:
                    # List what's in target/release to help debug
                    print(f"    Warning: Could not find binary for {dir_name}")
                    print(f"    Available files in {target_dir}:")
                    if target_dir.exists():
                        for f in target_dir.iterdir():
                            if f.is_file() and os.access(f, os.X_OK):
                                print(f"      - {f.name}")
                    
            except subprocess.CalledProcessError as e:
                print(f"[!] Failed to build {dir_name}: {e}")
                success = False
        
        return success
    
    def uninstall(self) -> bool:
        for binary in ["stardust-xr-server", "stardust-xr-flatland", "stardust-xr-protostar", 
                       "stardust-xr-hexagon_launcher", "flatland", "hexagon_launcher"]:
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
        # Also check flatpak location
        flatpak_dir = Path.home() / ".var" / "app" / "com.valvesoftware.Steam" / ".steam" / "steam" / "steamapps" / "common" / "SteamVR" / "drivers" / "vrto3d"
        if flatpak_dir.exists():
            return ComponentStatus.INSTALLED
        return ComponentStatus.NOT_INSTALLED
    
    def install(self, distro: Distro, hardware: HardwareInfo) -> bool:
        print(f"[*] Installing {self.name}...")
        
        # Find SteamVR drivers directory
        steamvr_locations = [
            Path.home() / ".steam" / "steam" / "steamapps" / "common" / "SteamVR" / "drivers",
            Path.home() / ".local" / "share" / "Steam" / "steamapps" / "common" / "SteamVR" / "drivers",
            Path.home() / ".var" / "app" / "com.valvesoftware.Steam" / ".steam" / "steam" / "steamapps" / "common" / "SteamVR" / "drivers",
        ]
        
        steamvr_drivers = None
        for loc in steamvr_locations:
            if loc.exists():
                steamvr_drivers = loc
                break
        
        if not steamvr_drivers:
            print("[!] SteamVR not found. Please install SteamVR first, then re-run this installer.")
            return False
        
        # Install build dependencies
        deps = {
            Distro.UBUNTU: ["build-essential", "cmake"],
            Distro.DEBIAN: ["build-essential", "cmake"],
            Distro.FEDORA: ["gcc-c++", "cmake"],
            Distro.ARCH: ["base-devel", "cmake"],
        }
        
        distro_deps = deps.get(distro, [])
        if distro_deps:
            install_packages(distro_deps, distro)
        
        src_dir = CACHE_DIR / "vrto3d"
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        
        if not clone_or_update("https://github.com/oneup03/VRto3D.git", src_dir):
            return False
        
        # Build
        try:
            run("cmake -B build", cwd=str(src_dir), shell=True)
            run("cmake --build build --config Release", cwd=str(src_dir), shell=True)
            
            vrto3d_dest = steamvr_drivers / "vrto3d"
            if vrto3d_dest.exists():
                shutil.rmtree(vrto3d_dest)
            
            # Copy built driver
            built_driver = src_dir / "build" / "vrto3d"
            if built_driver.exists():
                shutil.copytree(built_driver, vrto3d_dest)
            else:
                print(f"[!] Built driver not found at {built_driver}")
                return False
            
            return True
        except subprocess.CalledProcessError as e:
            print(f"[!] Build failed: {e}")
            return False
    
    def uninstall(self) -> bool:
        locations = [
            Path.home() / ".steam" / "steam" / "steamapps" / "common" / "SteamVR" / "drivers" / "vrto3d",
            Path.home() / ".local" / "share" / "Steam" / "steamapps" / "common" / "SteamVR" / "drivers" / "vrto3d",
            Path.home() / ".var" / "app" / "com.valvesoftware.Steam" / ".steam" / "steam" / "steamapps" / "common" / "SteamVR" / "drivers" / "vrto3d",
        ]
        for loc in locations:
            if loc.exists():
                shutil.rmtree(loc)
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
        deps_map = {
            Distro.UBUNTU: ["p7zip-full", "curl", "wget"],
            Distro.DEBIAN: ["p7zip-full", "curl", "wget"],
            Distro.FEDORA: ["p7zip", "curl", "wget"],
            Distro.ARCH: ["p7zip", "curl", "wget"],
        }
        deps = deps_map.get(distro, ["p7zip", "curl", "wget"])
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
        BIN_DIR.mkdir(parents=True, exist_ok=True)
        launcher = BIN_DIR / "reshade-setup"
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
║             VRStack Installer v0.2.0                         ║
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
    
    # Handle input - try to get from terminal if stdin is a pipe
    try:
        if not sys.stdin.isatty():
            # Try to reattach to terminal
            try:
                sys.stdin = open('/dev/tty', 'r')
            except OSError:
                print("Non-interactive mode detected. Use --minimal, --full, or --components flags.")
                return selected
        
        choice = input(f"{Colors.CYAN}Selection (numbers or names, 'all', or Enter for core only): {Colors.RESET}").strip()
    except EOFError:
        print("Non-interactive mode detected. Use --minimal, --full, or --components flags.")
        return selected
    
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
    
    # Handle input for confirmation
    try:
        if not sys.stdin.isatty():
            try:
                sys.stdin = open('/dev/tty', 'r')
            except OSError:
                print("Non-interactive mode: proceeding with installation...")
                confirm = 'y'
        else:
            confirm = input(f"{Colors.CYAN}Proceed with installation? [Y/n]: {Colors.RESET}").strip().lower()
    except EOFError:
        confirm = 'y'  # Default to yes in non-interactive mode
    
    if confirm and confirm != 'y' and confirm != '':
        print("Installation cancelled.")
        return False
    
    print()
    success = True
    for name in ordered:
        c = get_component(name)
        if c.check_installed() == ComponentStatus.INSTALLED:
            continue
        
        try:
            if not c.install(distro, hardware):
                print(f"{Colors.RED}[!] Failed to install {name}{Colors.RESET}")
                success = False
            else:
                print(f"{Colors.GREEN}[✓] Installed {name}{Colors.RESET}")
                c.configure(hardware)
        except Exception as e:
            print(f"{Colors.RED}[!] Error installing {name}: {e}{Colors.RESET}")
            success = False
    
    return success

# ============================================================================
# Main Entry Point
# ============================================================================

def main():
    parser = argparse.ArgumentParser(description="VRStack Installer")
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
        print(f"  3. Run 'xreal-launch status' to check system status")
        print(f"  4. Check the wiki: https://github.com/bl4ckj4ck777/VRStack")
    else:
        print(f"\n{Colors.YELLOW}Installation completed with some errors.{Colors.RESET}")
        print("Check the output above for details.")

if __name__ == "__main__":
    main()
