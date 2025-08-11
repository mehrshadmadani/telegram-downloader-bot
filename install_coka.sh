#!/bin/bash

# =============================================================
#         Coka Bot Manager - Interactive Installer v3.0
# =============================================================

COKA_SCRIPT_PATH="/usr/local/bin/coka"

# --- Functions ---
print_info() { echo -e "\e[34mINFO: $1\e[0m"; }
print_success() { echo -e "\e[32mSUCCESS: $1\e[0m"; }
print_error() { echo -e "\e[31mERROR: $1\e[0m"; }
print_warning() { echo -e "\e[33mWARNING: $1\e[0m"; }

# Check for root privileges
if [ "$(id -u)" -ne 0 ]; then
  print_error "This script must be run with sudo or as root."
  exit 1
fi

# --- Interactive Setup ---
print_info "Welcome to the Coka Bot Manager Interactive Installer!"
echo

# Ask for the bot directory path
read -p "Please enter the full path to your bot directory (e.g., /root/telegram-downloader-bot): " BOT_DIR_INPUT
BOT_DIR=${BOT_DIR_INPUT:-/root/telegram-downloader-bot} # Default value if empty

# Ask for the worker's raw GitHub URL
read -p "Please enter the raw GitHub URL for advanced_worker.py: " WORKER_URL_INPUT
WORKER_URL=${WORKER_URL_INPUT:-https://raw.githubusercontent.com/mehrshadmadani/telegram-downloader-bot/main/advanced_worker.py} # Default value

echo
print_info "Using the following settings:"
echo "Bot Directory: $BOT_DIR"
echo "Worker URL: $WORKER_URL"
echo

read -p "Are these settings correct? (y/n): " CONFIRM
if [[ "$CONFIRM" != "y" ]]; then
    print_error "Installation cancelled by user."
    exit 1
fi

# --- Installation ---
print_info "Installing required utilities (screen, curl)..."
apt-get update > /dev/null 2>&1
apt-get install -y screen curl > /dev/null 2>&1
print_success "Utilities are ready."

print_info "Creating the 'coka' management script with your settings..."

# --- Writing the coka script content using a Here Document ---
cat > "$COKA_SCRIPT_PATH" << EOF
#!/bin/bash
# =============================================================
#         Coka Bot - Worker Management Script
# =============================================================

# --- Tanzimat (Settings) ---
VERSION="3.0 (Control Panel)"
BOT_DIR="$BOT_DIR"
WORKER_GITHUB_URL="$WORKER_URL"
WORKER_SCREEN_NAME="worker_session"

# --- Functions ---
print_info() { echo -e "\e[34mINFO: \$1\e[0m"; }
print_success() { echo -e "\e[32mSUCCESS: \$1\e[0m"; }
print_error() { echo -e "\e[31mERROR: \$1\e[0m"; }
print_warning() { echo -e "\e[33mWARNING: \$1\e[0m"; }

is_worker_running() {
    screen -list | grep -q "\$WORKER_SCREEN_NAME"
}

# --- Main Script Logic ---
cd "\$BOT_DIR" || { print_error "Directory not found: \$BOT_DIR"; exit 1; }

case "\$1" in
    start)
        # ... (start logic from previous response) ...
        ;;
    stop)
        # ... (stop logic from previous response) ...
        ;;
    restart)
        # ... (restart logic from previous response) ...
        ;;
    status)
        SERVER_IP=\$(hostname -I | awk '{print \$1}')
        COKA_VERSION=\$(grep -oP 'VERSION="\K[^"]+' /usr/local/bin/coka)
        
        echo -e "\e[1;35m
    ╔════════════════════════════════════════════════════╗
    ║             COKA BOT CONTROL PANEL                 ║
    ╚════════════════════════════════════════════════════╝\e[0m"
        echo
        echo -e "  \e[1mServer IP:\e[0m \e[33m\$SERVER_IP\e[0m"
        echo -e "  \e[1mManager Version:\e[0m \e[36mv\$COKA_VERSION\e[0m"
        
        if is_worker_running; then
            STATUS_TEXT="\e[1;32mRUNNING\e[0m"
        else
            STATUS_TEXT="\e[1;31mSTOPPED\e[0m"
        fi
        echo -e "  \e[1mWorker Status:\e[0m \$STATUS_TEXT"
        echo
        echo -e "\e[2m----------------------------------------------------------\e[0m"
        ;;
    logs)
        # ... (logs logic from previous response) ...
        ;;
    update)
        # ... (update logic from previous response) ...
        ;;
    *)
        coka status
        echo
        echo "Dastoorat-e Mojood (Available commands):"
        echo "  coka start         - Start/Restart kardan-e worker"
        echo "  coka stop          - Stop kardan-e worker"
        echo "  coka restart       - Restart kardan-e worker"
        echo "  coka logs [file|live] - Namayesh-e log-ha"
        echo "  coka update        - Update kardan-e worker az GitHub"
        ;;
esac
EOF

# --- Final Step: Make it executable ---
chmod +x "$COKA_SCRIPT_PATH"

print_success "Management script 'coka' installed successfully!"
echo
print_info "You can now manage your worker by typing 'coka' from anywhere on the server."
echo
coka status
