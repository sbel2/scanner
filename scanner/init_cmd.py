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
            "CLAUDE_CODE_OAUTH_TOKEN=\n"
            "TAVILY_API_KEY=tvly-...\n"
            "RESEND_API_KEY=re_...\n"
        )
        print(f"[ok]   Created blank .env at {ENV_FILE}")


def _check_dependencies():
    missing = []
    for pkg, import_name in [
        ("pyyaml", "yaml"),
        ("resend", "resend"),
        ("httpx", "httpx"),
        ("tavily-python", "tavily"),
        ("pydantic", "pydantic"),
        ("jinja2", "jinja2"),
        ("python-dotenv", "dotenv"),
        ("claude-agent-sdk", "claude_agent_sdk"),
    ]:
        try:
            __import__(import_name)
        except ImportError:
            missing.append(pkg)

    if missing:
        print(f"[warn] Missing packages: {', '.join(missing)}")
        print("       Run: pip install -r requirements.txt")
    else:
        print("[ok]   All Python dependencies are installed.")


def _check_claude_code():
    """Check if Claude Code is installed and guide the user through setup-token."""
    claude_path = shutil.which("claude")
    if not claude_path:
        print()
        print("[warn] Claude Code is not installed or not on your PATH.")
        print()
        print("  Claude Code is required for LLM scoring. Install it here:")
        print("    https://claude.ai/download")
        print()
        print("  After installing, run this wizard again:")
        print("    python -m scanner init")
        return

    print(f"[ok]   Claude Code found at {claude_path}")

    # Check if a token is already in .env
    token_set = False
    if ENV_FILE.exists():
        content = ENV_FILE.read_text()
        for line in content.splitlines():
            if line.startswith("CLAUDE_CODE_OAUTH_TOKEN=") and len(line.split("=", 1)[1].strip()) > 10:
                token_set = True
                break

    if token_set:
        print("[ok]   CLAUDE_CODE_OAUTH_TOKEN already set in .env")
        return

    print()
    print("─" * 60)
    print("  CLAUDE AUTH SETUP")
    print("─" * 60)
    print()
    print("  Scanner uses your Claude Pro/Max subscription for LLM calls.")
    print("  You need to generate a long-lived token (valid for 1 year).")
    print()
    print("  Run this command now:")
    print()
    print("    claude setup-token")
    print()
    print("  It will print a token. Copy it, then paste it into your .env:")
    print()
    print("    CLAUDE_CODE_OAUTH_TOKEN=<paste token here>")
    print()
    print("  This token lets Scanner run headlessly every day without")
    print("  requiring you to log in again.")
    print()

    # Offer to run setup-token interactively
    try:
        answer = input("  Run `claude setup-token` now? [y/N] ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        answer = "n"

    if answer == "y":
        print()
        try:
            subprocess.run(["claude", "setup-token"], check=False)
        except Exception as e:
            print(f"[warn] Could not run claude setup-token: {e}")
        print()
        print("  Copy the token above and add it to your .env file:")
        print(f"    {ENV_FILE}")
        print()
        print("  Line to add/update:")
        print("    CLAUDE_CODE_OAUTH_TOKEN=<your token>")
    else:
        print("  [info] Skipped. Remember to add your token to .env before running.")


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
        except subprocess.CalledProcessError as e:
            print(f"[warn] launchctl load failed: {e.stderr.decode().strip()}")
            print(f"       You can manually load it: launchctl load {dest}")
    else:
        print(f"[info] Copy {plist_path} to ~/Library/LaunchAgents/ to schedule daily runs.")


def _setup_cron():
    """Write an install_cron.sh helper for Linux."""
    python_path = sys.executable
    working_dir = str(ROOT)
    cron_line = (
        f"0 8 * * * cd {working_dir} && {python_path} -m scanner run"
        f" >> {working_dir}/logs/scanner.out.log"
        f" 2>> {working_dir}/logs/scanner.err.log"
    )

    cron_helper = ROOT / "install_cron.sh"
    cron_helper.write_text(
        f"#!/bin/bash\n"
        f"# Run this script to install the daily cron job\n"
        f'(crontab -l 2>/dev/null; echo "{cron_line}") | crontab -\n'
        f'echo "Cron job installed. Runs daily at 08:00."\n'
    )
    cron_helper.chmod(0o755)

    print()
    print("[info] To schedule daily runs, add this cron entry:")
    print(f"       crontab -e")
    print()
    print(f"       {cron_line}")
    print()
    print(f"[ok]   Or just run: bash {cron_helper}")


def _all_keys_present() -> tuple[bool, list[str]]:
    """Return (ready, missing_keys) based on what is set in .env."""
    from dotenv import dotenv_values
    env = dotenv_values(ENV_FILE) if ENV_FILE.exists() else {}

    missing = []

    # Claude auth: either OAuth token or API key
    oauth = env.get("CLAUDE_CODE_OAUTH_TOKEN", "").strip()
    api_key = env.get("ANTHROPIC_API_KEY", "").strip()
    if not oauth and not api_key:
        missing.append("CLAUDE_CODE_OAUTH_TOKEN (or ANTHROPIC_API_KEY)")

    if not env.get("TAVILY_API_KEY", "").strip().startswith("tvly-") or \
       env.get("TAVILY_API_KEY", "").strip() == "tvly-...":
        missing.append("TAVILY_API_KEY")

    if not env.get("RESEND_API_KEY", "").strip().startswith("re_") or \
       env.get("RESEND_API_KEY", "").strip() == "re_...":
        missing.append("RESEND_API_KEY")

    return len(missing) == 0, missing


def _mission_filled_out() -> bool:
    """Check that mission.yaml has been filled in (not just the template defaults)."""
    if not MISSION_FILE.exists():
        return False
    content = MISSION_FILE.read_text(encoding="utf-8")
    # The template leaves placeholder text — if the user hasn't changed the name field it's a sign
    return "Your Name" not in content and "your.email@example.com" not in content


def _fire_first_send():
    """Check readiness and fire the first real digest send."""
    print()
    print("─" * 60)
    print("  FIRST SEND")
    print("─" * 60)
    print()

    ready, missing = _all_keys_present()
    mission_ok = _mission_filled_out()

    if not mission_ok:
        print("[skip] mission.yaml still has placeholder values.")
        print(f"       Fill it out at: {MISSION_FILE}")
        print("       Then run: python -m scanner run --welcome")
        return

    if not ready:
        print("[skip] The following keys are missing or still set to placeholder values:")
        for k in missing:
            print(f"         • {k}")
        print(f"\n       Add them to: {ENV_FILE}")
        print("       Then run: python -m scanner run --welcome")
        return

    print("[ok]   All keys are set and mission.yaml is filled out.")
    print()
    print("  Kicking off your first scan now — this may take a minute or two.")
    print("  A digest will be sent to the email in your mission.yaml.")
    print()

    try:
        result = subprocess.run(
            [sys.executable, "-m", "scanner", "run", "--welcome"],
            cwd=str(ROOT),
            check=False,
        )
        if result.returncode == 0:
            print()
            print("=" * 60)
            print("  SCANNER IS LIVE")
            print("=" * 60)
            print()
            print("  Your first digest has been sent.")
            print("  From now on, a new digest will arrive every morning at 08:00.")
            print()
            print("  To tune what you receive, edit:")
            print(f"    {MISSION_FILE}")
            print()
        else:
            print()
            print("[warn] The first run encountered an error.")
            print("       Check the output above for details.")
            print("       Once fixed, re-run: python -m scanner run --welcome")
    except Exception as e:
        print(f"[warn] Could not launch scanner: {e}")
        print("       Run manually: python -m scanner run --welcome")


def run():
    _print_header()
    _check_python_version()
    _create_mission_file()
    _create_env_file()
    _check_dependencies()
    _check_claude_code()

    system = platform.system()
    print()
    if system == "Darwin":
        print("[info] macOS detected — setting up launchd daily schedule...")
        _setup_launchd()
    else:
        print(f"[info] {system} detected — providing cron setup instructions...")
        _setup_cron()

    _fire_first_send()
