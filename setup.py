#!/usr/bin/env python3
"""
NAVE Setup Script - One-command environment setup
Run: python setup.py
"""

import os
import sys
import subprocess
import shutil
from pathlib import Path


def run_command(cmd, cwd=None, check=True):
    """Run a command and return the result"""
    try:
        result = subprocess.run(
            cmd,
            shell=True,
            cwd=cwd,
            capture_output=True,
            text=True,
            check=check
        )
        return result.returncode == 0, result.stdout.strip(), result.stderr.strip()
    except subprocess.CalledProcessError as e:
        return False, "", str(e)


def print_status(message):
    print(f"🔧 {message}")


def print_success(message):
    print(f"✅ {message}")


def print_error(message):
    print(f"❌ {message}")


def check_requirements():
    """Check if required tools are available"""
    required_tools = ['python3', 'pip3']
    missing = []

    for tool in required_tools:
        if not shutil.which(tool):
            missing.append(tool)

    if missing:
        print_error(f"Missing required tools: {', '.join(missing)}")
        print("Please install them and try again.")
        return False

    return True


def setup_mise():
    """Setup mise if available"""
    if shutil.which('mise'):
        print_status("Setting up mise...")
        success, _, _ = run_command("mise install python@3.12")
        if success:
            print_success("Python 3.12 installed via mise")
            return True
        else:
            print_status("Using system Python")
    return False


def create_venv():
    """Create virtual environment"""
    print_status("Creating virtual environment...")

    # Use mise Python if available, otherwise system Python
    python_cmd = "mise exec python -- python"
    if not run_command(f"{python_cmd} --version")[0]:
        python_cmd = "python3"

    success, _, _ = run_command(f"{python_cmd} -m venv .venv")
    if not success:
        print_error("Failed to create virtual environment")
        return False

    print_success("Virtual environment created")
    return True


def install_dependencies():
    """Install dependencies from requirements.txt"""
    print_status("Installing dependencies...")

    pip_cmd = ".venv/bin/pip"
    success, _, _ = run_command(f"{pip_cmd} install --upgrade pip")

    if os.path.exists("requirements.txt"):
        # Install dependencies from requirements.txt
        success, _, _ = run_command(
            f"{pip_cmd} install -r requirements.txt"
        )
        if success:
            print_success("Dependencies installed successfully")
        else:
            print_error("Failed to install dependencies")
            return False

    # Install editable for CLI entrypoint (uses pyproject.toml)
    print_status("Installing editable package for nave CLI...")
    success, _, _ = run_command(f"{pip_cmd} install -e .")
    if success:
        print_success("Editable install complete - 'nave' command available")
    else:
        print_status(
            "Editable install skipped (CLI may require manual pip install -e .)")

    return True


def setup_direnv():
    """Setup direnv if available"""
    if shutil.which('direnv'):
        print_status("Setting up direnv...")
        success, _, _ = run_command("direnv allow")
        if success:
            print_success(
                "direnv configured - environment will activate automatically")
        else:
            print_status("direnv available but configuration failed")
    else:
        print_status(
            "direnv not found - install it for automatic environment activation")


def create_scripts():
    """Create utility scripts"""
    print_status("Creating utility scripts...")

    # Create a simple run script
    run_script = '''#!/bin/bash
# Simple script runner for NAVE
# Usage: ./run.sh <script_name> [args...]

if [ $# -eq 0 ]; then
    echo "Usage: ./run.sh <script_name> [args...]"
    echo "Available scripts:"
    ls scripts/*.py 2>/dev/null || echo "No scripts found"
    exit 1
fi

SCRIPT_NAME="$1"
shift

if [ -f "scripts/${SCRIPT_NAME}.py" ]; then
    python "scripts/${SCRIPT_NAME}.py" "$@"
elif [ -f "scripts/${SCRIPT_NAME}" ]; then
    python "scripts/${SCRIPT_NAME}" "$@"
else
    echo "Script '${SCRIPT_NAME}' not found in scripts/ directory"
    exit 1
fi
'''
    with open('run.sh', 'w') as f:
        f.write(run_script)
    os.chmod('run.sh', 0o755)

    print_success("Utility scripts created")


def main():
    """Main setup function"""
    print("🚀 NAVE Environment Setup")
    print("=" * 50)

    if not check_requirements():
        return 1

    # Setup components
    setup_mise()
    create_venv()
    install_dependencies()
    setup_direnv()
    create_scripts()

    print("\n" + "=" * 50)
    print_success("NAVE setup complete!")
    print("\n🎯 How to use NAVE:")
    print("1. Enter directory: cd /path/to/nave")
    print("2. Environment activates automatically (if direnv installed)")
    print("3. Or manually: source .venv/bin/activate")
    print("4. Use unified CLI: nave --help")
    print("5. Run scripts: python scripts/your_script.py or ./run.sh script_name")
    print("\n📚 Available commands:")
    print("- nave --help                  # Unified CLI")
    print("- nave trading run-strategy    # Run strategies")
    print("- nave api start               # Start FastAPI backend")
    print("- nave mcp                     # Start MCP server")
    print("- python --version             # Check Python version")
    print("- pip list                     # List installed packages")
    print("- ./run.sh script_name         # Legacy script runner")

    return 0


if __name__ == "__main__":
    sys.exit(main())
