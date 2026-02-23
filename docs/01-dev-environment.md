# 01 — Development Environment Setup

## Why bother before the board arrives?

Yocto builds are heavy. They hammer CPU, RAM, and disk for hours. Getting the host PC ready now means you can hit the ground running the moment hardware shows up. Don't wait.

## Picking a Linux environment

| Approach | Pros | Cons | Verdict |
|----------|------|------|---------|
| Ubuntu dual-boot | Best performance, 100% compatible | Needs a dedicated partition, reboot to switch | **Best option** |
| WSL2 (Windows) | No reboot, convenient | Slow I/O, USB passthrough is painful, Yocto build times roughly double | Workable but not great |
| VMware / VirtualBox | Good isolation | ~20% performance hit, needs more disk | Fallback |

I went with **Ubuntu 22.04 LTS (Jammy Jellyfish)** — it's the environment NXP tests their BSP against, so you avoid surprises.

## Hardware requirements

| Resource | Minimum | Recommended |
|----------|---------|-------------|
| CPU | 4 cores | 8+ cores |
| RAM | 8 GB | 16 GB+ (Yocto eats memory) |
| Disk | 100 GB | 250 GB+ SSD (build artifacts alone hit ~100 GB) |
| Network | Stable connection | A proxy or mirror helps when pulling source tarballs |

## Installing system dependencies

### Ubuntu 22.04 base packages

```bash
sudo apt update && sudo apt upgrade -y

# Yocto build dependencies (per Yocto Scarthgap docs)
sudo apt install -y \
  gawk wget git diffstat unzip texinfo gcc build-essential \
  chrpath socat cpio python3 python3-pip python3-pexpect \
  xz-utils debianutils iputils-ping python3-git python3-jinja2 \
  python3-subunit zstd liblz4-tool file locales libacl1 \
  lz4 python3-distutils

# Extra tools you'll want sooner or later
sudo apt install -y \
  minicom picocom screen \
  device-tree-compiler \
  u-boot-tools \
  libssl-dev \
  bc \
  bison flex \
  libncurses-dev \
  rsync
```

### Locale setup

Some build scripts assume `en_US.UTF-8`. Set it explicitly:

```bash
sudo locale-gen en_US.UTF-8
sudo update-locale LANG=en_US.UTF-8
```

## Git configuration

```bash
git config --global user.name "Your Name"
git config --global user.email "your@email.com"
git config --global color.ui auto
```

## Installing Google's `repo` tool

NXP's BSP is spread across multiple Git repositories. Google's `repo` tool manages them as a group:

```bash
mkdir -p ~/.bin
curl https://storage.googleapis.com/git-repo-downloads/repo > ~/.bin/repo
chmod a+x ~/.bin/repo
echo 'export PATH="${HOME}/.bin:${PATH}"' >> ~/.bashrc
source ~/.bashrc
repo version
```

## ARM GCC cross-compilers

You need two toolchains: one for the A-core Linux userspace (AArch64), and one for the M7 core (bare-metal / FreeRTOS).

### Option 1: APT install (quick and easy)

```bash
sudo apt install -y gcc-aarch64-linux-gnu g++-aarch64-linux-gnu
sudo apt install -y gcc-arm-none-eabi    # for M7 bare-metal / FreeRTOS

aarch64-linux-gnu-gcc --version
arm-none-eabi-gcc --version
```

### Option 2: ARM's official toolchain (better for M7 work)

Download `arm-gnu-toolchain-13.x.x-x86_64-arm-none-eabi` from the [ARM Developer site](https://developer.arm.com/downloads/-/arm-gnu-toolchain-downloads) and extract it:

```bash
sudo tar xf arm-gnu-toolchain-*.tar.xz -C /opt/
echo 'export PATH="/opt/arm-gnu-toolchain-13.3.rel1-x86_64-arm-none-eabi/bin:${PATH}"' >> ~/.bashrc
source ~/.bashrc
```

On my setup I use the APT version for AArch64 and the ARM official toolchain for the M7 — keeps things simple.

## CMake

```bash
# Via snap (gets you a recent version easily)
sudo snap install cmake --classic

# Or via APT if you prefer
sudo apt install -y cmake

cmake --version   # needs to be >= 3.20
```

## west (MCUXpresso SDK management)

`west` is Zephyr's meta-tool, but NXP also uses it for MCUXpresso SDK:

```bash
pip3 install west
west --version
```

## VS Code setup

### Installation

Grab the `.deb` package from <https://code.visualstudio.com/> and install it.

### Recommended extensions

| Extension | What it does |
|-----------|-------------|
| C/C++ (Microsoft) | IntelliSense, debugging |
| CMake Tools | CMake project integration |
| Device Tree | Syntax highlighting for `.dts` / `.dtsi` |
| Remote - SSH | Remote development (handy if you're using a VM) |
| Serial Monitor | Built-in serial port viewer |
| BitBake | Syntax highlighting for Yocto recipes |
| Cortex-Debug | ARM debug sessions via GDB |

### Suggested `settings.json`

```json
{
  "C_Cpp.default.compilerPath": "/usr/bin/aarch64-linux-gnu-gcc",
  "C_Cpp.default.intelliSenseMode": "linux-gcc-arm64",
  "files.associations": {
    "*.bb": "bitbake",
    "*.bbappend": "bitbake",
    "*.conf": "bitbake"
  }
}
```

## Verification checklist

Run through these before moving on. If any fail, fix them now — you don't want to discover a missing package halfway through a 3-hour Yocto build.

- [ ] `git --version` — 2.x+
- [ ] `repo version` — prints version info
- [ ] `aarch64-linux-gnu-gcc --version` — prints version info
- [ ] `arm-none-eabi-gcc --version` — prints version info
- [ ] `cmake --version` — 3.20+
- [ ] `west --version` — prints version info
- [ ] `python3 --version` — 3.10+
- [ ] Free disk space > 200 GB (`df -h`)

## What's next

Once the environment is ready and the board is in hand, move on to the Yocto BSP build: [03-Yocto-BSP.md](03-Yocto-BSP.md)
