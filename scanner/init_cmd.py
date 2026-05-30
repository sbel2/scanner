"""
scanner init — one-time setup wizard.

Usage:
    python -m scanner init
"""
from __future__ import annotations

import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MISSION_TEMPLATE = ROOT / "mission.yaml.template"
MISSION_FILE = ROOT / "mission.yaml"
ENV_EXAMPLE = ROOT / ".env.example"
ENV_FILE = ROOT / ".env"
LAUNCHD_TEMPLATE = ROOT / "launchd" / "com.user.scanner.plist"
LAUNCHD_TEMPLATE_GENERIC = ROOT / "launchd" / "com.scanner.plist.template"


def _print_header():
    print()
    print("=" * 60)
    print("  SCANNER — Setup Wizard")
    print("=" * 60)
    print()


def _check_python_version():
    if sys.version_info < (3, 11):
        print("[error] Python 3.11+ is required.")
        sys.exit(1)


def _create_mission_file():
    if MISSION_FILE.exists():
        print(f"[skip] mission.yaml already exists at {MISSION_FILE}")
        return
    if not MISSION_TEMPLATE.exists():
        print(f"[error] Template not found: {MISSION_TEMPLATE}")
        sys.exit(1)
    shutil.copy(MISSION_TEMPLATE, MISSION_FILE)
    print(f"[ok]   Created mission.yaml at {MISSION_FILE}")


def _create_env_file():
    if ENV_FILE.exists():
        print(f"[skip] .env already exists at {ENV_FILE}")
        return
    if ENV_EXAMPLE.exists():
        shutil.copy(ENV_EXAMPLE, ENV_FILE)
        print(f"[ok]   Created .env from .env.example at {ENV_FILE}")
    else:
        ENV_FILE.write_text(
            "TAVILY_API_KEY=tvly-...\n"
            "RESEND_API_KEY=re_...\n"
            "ANTHROPIC_API_KEY=sk-ant-...\n"
        )
        print(f"[ok]   Created blank .env at {ENV_FILE}")


def _check_dependencies():
    try:
        import yaml  # noqa: F401
        import anthropic  # noqa: F401
        import resend  # noqa: F401
        import tavily  # noqa: F401
        import jinja2  # noqa: F401
        import pydantic  # noqa: F401
        print("[ok]   All Python dependencies are installed.")
    except ImportError as e:
        print(f"[warn] Missing dependency: {e}")
        print("       Run: pip install -r requirements.txt")


def _setup_launchd():
    """Generate a personalized launchd plist for macOS."""
    python_path = sys.executable
    working_dir = str(ROOT)
    home_dir = str(Path.home())
    label = "com.scanner.daily"

    plist_content = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>{label}</string>
    <key>ProgramArguments</key>
    <array>
        <string>{python_path}</string>
        <string>-m</string>
        <string>scanner</string>
        <string>run</string>
    </array>
    <key>WorkingDirectory</key>
    <string>{working_dir}</string>
    <key>EnvironmentVariables</key>
    <dict>
        <key>HOME</key>
        <string>{home_dir}</string>
        <key>PATH</key>
        <string>/usr/local/bin:/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin</string>
    </dict>
    <key>StartCalendarInterval</key>
    <dict>
        <key>Hour</key>
        <integer>8</integer>
        <key>Minute</key>
        <integer>0</integer>
    </dict>
    <key>StandardOutPath</key>
    <string>{working_dir}/logs/scanner.out.log</string>
    <key>StandardErrorPath</key>
    <string>{working_dir}/logs/scanner.err.log</string>
    <key>RunAtLoad</key>
    <false/>
</dict>
</plist>
"""
    plist_dir = ROOT / "launchd"
    plist_dir.mkdir(exist_ok=True)
    plist_path = plist_dir / f"{label}.plist"
    plist_path.write_text(plist_content)
    print(f"[ok]   Generated launchd plist at {plist_path}")

    agents_dir = Path.home() / "Library" / "LaunchAgents"
    dest = agents_dir / f"{label}.plist"
    if agents_dir.exists():
        shutil.copy(plist_path, dest)
        try:
            subprocess.run(["launchctl", "load", str(dest)], check=True, capture_output=True)
            print(f"[ok]   Installed and loaded launchd agent: {label}")
            print(f"       Runs daily at 08:00. To test now: launchctl start {label}")
        except subprocess.CalledProcessError as e:
            print(f"[warn] launchctl load failed: {e.stderr.decode().strip()}")
            print(f"       You can manually load it: launchctl load {dest}")
    else:
        print(f"[info] Copy {plist_path} to ~/Library/LaunchAgents/ to schedule daily runs.")


def _setup_cron():
    """Add a cron job for Linux/non-macOS systems."""
    python_path = sys.executable
    working_dir = str(ROOT)
    cron_line = f"0 8 * * * cd {working_dir} && {python_path} -m scanner run >> {working_dir}/logs/scanner.out.log 2>> {working_dir}/logs/scanner.err.log"

    print()
    print("[info] To schedule daily runs on Linux, add this line to your crontab:")
    print(f"       crontab -e")
    print()
    print(f"       {cron_line}")
    print()

    # Write a helper script
    cron_helper = ROOT / "install_cron.sh"
    cron_helper.write_text(
        f"#!/bin/bash\n"
        f"# Run this script to install the daily cron job\n"
        f'(crontab -l 2>/dev/null; echo "{cron_line}") | crontab -\n'
        f'echo "Cron job installed. Runs daily at 08:00."\n'
    )
    cron_helper.chmod(0o755)
    print(f"[ok]   Wrote install_cron.sh — run it to auto-install the cron job.")


def _print_next_steps():
    print()
    print("=" * 60)
    print("  NEXT STEPS")
    print("=" * 60)
    print()
    print("  1. Fill out your mission file:")
    print(f"       {MISSION_FILE}")
    print()
    print("  2. Add your API keys to .env:")
    print(f"       {ENV_FILE}")
    print()
    print("     Keys you need (all have free tiers):")
    print("       ANTHROPIC_API_KEY  — https://console.anthropic.com/")
    print("       TAVILY_API_KEY     — https://app.tavily.com/  (1,000 free/mo)")
    print("       RESEND_API_KEY     — https://resend.com/  (free tier)")
    print()
    print("  3. Test with a dry run (no email sent):")
    print("       SCANNER_DRY_RUN=1 python -m scanner run")
    print()
    print("  4. Run for real:")
    print("       python -m scanner run")
    print()
    print("  Daily scheduling has been configured above.")
    print()


def run():
    _print_header()
    _check_python_version()
    _create_mission_file()
    _create_env_file()
    _check_dependencies()

    system = platform.system()
    print()
    if system == "Darwin":
        print("[info] macOS detected — setting up launchd daily schedule...")
        _setup_launchd()
    else:
        print(f"[info] {system} detected — providing cron setup instructions...")
        _setup_cron()

    _print_next_steps()
