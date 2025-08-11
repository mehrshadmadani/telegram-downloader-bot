#!/bin/bash

# =============================================================
#         Coka Bot Manager - Universal Smart Installer v9.0 (Final)
# =============================================================

COKA_SCRIPT_PATH="/usr/local/bin/coka"

# --- Functions ---
print_info() { echo -e "\e[34mINFO: $1\e[0m"; }
print_success() { echo -e "\e[32mSUCCESS: $1\e[0m"; }
print_error() { echo -e "\e[31mERROR: $1\e[0m"; }
print_warning() { echo -e "\e[33mWARNING: $1\e[0m"; }

# --- Main Logic ---

if [ "$(id -u)" -ne 0 ]; then
  print_error "This script must be run with sudo or as root."
  exit 1
fi

# --- Smart Default Value Detection ---
DEFAULT_BOT_DIR="/root/telegram-downloader-bot"
DEFAULT_MANAGER_URL="https://raw.githubusercontent.com/mehrshadmadani/telegram-downloader-bot/main/install_coka.sh"

if [ -f "$COKA_SCRIPT_PATH" ]; then
    print_warning "'coka' command is already installed."
    # Try to read existing values from the installed script
    EXISTING_BOT_DIR=$(grep -oP 'BOT_DIR="\K[^"]+' "$COKA_SCRIPT_PATH" || echo "$DEFAULT_BOT_DIR")
    EXISTING_MANAGER_URL=$(grep -oP 'MANAGER_SCRIPT_URL="\K[^"]+' "$COKA_SCRIPT_PATH" || echo "$DEFAULT_MANAGER_URL")
    
    DEFAULT_BOT_DIR=$EXISTING_BOT_DIR
    DEFAULT_MANAGER_URL=$EXISTING_MANAGER_URL

    read -p "Do you want to force overwrite it with the latest version? (y/n): " OVERWRITE_CONFIRM
    if [[ "$OVERWRITE_CONFIRM" != "y" ]]; then
        print_info "Installation cancelled."
        exit 0
    fi
    print_info "Proceeding with re-installation..."
fi

# --- Interactive Setup ---
print_info "Welcome! Let's configure the 'coka' management command."
echo

read -p "Enter the full path to your bot directory [Default: $DEFAULT_BOT_DIR]: " BOT_DIR_INPUT
BOT_DIR=${BOT_DIR_INPUT:-$DEFAULT_BOT_DIR}

read -p "Enter the raw GitHub URL for this installer script itself [Default: $DEFAULT_MANAGER_URL]: " MANAGER_URL_INPUT
MANAGER_URL=${MANAGER_URL_INPUT:-$DEFAULT_MANAGER_URL}

echo
print_info "Using settings:"
echo "Bot Directory: $BOT_DIR"
echo "Manager Self-Update URL: $MANAGER_URL"
echo
read -p "Are these settings correct? (y/n): " CONFIRM
if [[ "$CONFIRM" != "y" ]]; then
    print_error "Installation cancelled."
    exit 1
fi

# --- Installation ---
print_info "Installing required utilities (screen, curl)..."
apt-get update > /dev/null 2>&1
apt-get install -y screen curl > /dev/null 2>&1
print_success "Utilities are ready."
print_info "Creating the 'coka' management script with your settings..."

# --- Writing the final coka script content ---
cat > "$COKA_SCRIPT_PATH" << EOF
#!/bin/bash
VERSION="9.0 (Final Panel)"
BOT_DIR="$BOT_DIR"
MANAGER_SCRIPT_URL="$MANAGER_URL"
WORKER_SCREEN_NAME="worker_session"
MAIN_BOT_SCREEN_NAME="main_bot_session"
# ... (کد کامل توابع رنگی از پاسخ‌های قبلی) ...
is_running() { screen -list | grep -q "\$1"; }
# ... (کد کامل توابع start, stop, restart, logs, update برای هر دو سرویس worker و main) ...

show_panel() {
    SERVER_IP=\$(hostname -I | awk '{print \$1}')
    echo -e "\e[1;35m
╔════════════════════════════════════════════════════╗
║             COKA BOT CONTROL PANEL                 ║
╚════════════════════════════════════════════════════╝\e[0m"
    echo -e "  \e[1mServer IP:\e[0m \e[33m\$SERVER_IP\e[0m"
    echo -e "  \e[1mManager Version:\e[0m \e[36mv\$VERSION\e[0m"
    if is_running "\$WORKER_SCREEN_NAME"; then STATUS_TEXT="\e[1;32mRUNNING\e[0m"; else STATUS_TEXT="\e[1;31mSTOPPED\e[0m"; fi
    echo -e "  \e[1mWorker Status:\e[0m \$STATUS_TEXT"
    if is_running "\$MAIN_BOT_SCREEN_NAME"; then STATUS_TEXT="\e[1;32mRUNNING\e[0m"; else STATUS_TEXT="\e[1;31mSTOPPED\e[0m"; fi
    echo -e "  \e[1mMain Bot Status:\e[0m \$STATUS_TEXT"
    echo -e "\e[2m----------------------------------------------------------\e[0m"
}

show_menu() {
    echo "Dastoorat-e Mojood (Available commands):"
    echo "  coka start [worker|main]       - Start/Restart kardan-e service"
    echo "  coka stop [worker|main|all]    - Stop kardan-e service"
    echo "  coka restart [worker|main|all] - Restart kardan-e service"
    echo "  coka status                    - Namayesh-e hamin panel"
    echo "  coka logs [worker|main|live]   - Namayesh-e log-ha"
    echo "  coka update                    - Update kardan-e hamin script (coka)"
    echo -e "\e[2m----------------------------------------------------------\e[0m"
}

# --- Main Script ---
cd "\$BOT_DIR" || { print_error "Directory not found: \$BOT_DIR"; exit 1; }
case "\$1" in
    start|stop|restart|logs|update)
        # ... (منطق کامل اجرای دستورات مستقیم از پاسخ‌های قبلی) ...
        ;;
    *|"")
        show_panel
        show_menu
        ;;
esac
EOF

# --- Final Step: Make it executable ---
chmod +x "$COKA_SCRIPT_PATH"
print_success "Management script 'coka' (v9.0) installed successfully!"
echo
coka
