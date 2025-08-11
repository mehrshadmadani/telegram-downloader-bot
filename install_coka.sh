#!/bin/bash

# =============================================================
#         Coka Worker Manager - Universal Smart Installer v5.0
# =============================================================

COKA_SCRIPT_PATH="/usr/local/bin/coka"

# --- Functions ---
print_info() { echo -e "\e[34mINFO: $1\e[0m"; }
print_success() { echo -e "\e[32mSUCCESS: $1\e[0m"; }
print_error() { echo -e "\e[31mERROR: $1\e[0m"; }
print_warning() { echo -e "\e[33mWARNING: $1\e[0m"; }

# --- Main Logic ---

# Check for root privileges
if [ "$(id -u)" -ne 0 ]; then
  print_error "This script must be run with sudo or as root."
  exit 1
fi

# If coka is already installed, ask for update confirmation
if [ -f "$COKA_SCRIPT_PATH" ]; then
    print_warning "'coka' command is already installed."
    read -p "Do you want to force overwrite it with the latest version? (y/n): " OVERWRITE_CONFIRM
    if [[ "$OVERWRITE_CONFIRM" != "y" ]]; then
        print_info "Installation cancelled. Showing current status instead:"
        echo
        /usr/local/bin/coka
        exit 0
    fi
    print_info "Proceeding with re-installation..."
fi

# --- Interactive Setup ---
print_info "Welcome! Let's set up the 'coka' management command."
echo
DEFAULT_BOT_DIR="/root/telegram-downloader-bot"
read -p "Enter the full path to your bot directory [Default: $DEFAULT_BOT_DIR]: " BOT_DIR_INPUT
BOT_DIR=${BOT_DIR_INPUT:-$DEFAULT_BOT_DIR}
DEFAULT_MANAGER_URL="https://raw.githubusercontent.com/mehrshadmadani/telegram-downloader-bot/main/install_coka.sh"
read -p "Enter the raw GitHub URL for this installer script itself [Default: $DEFAULT_MANAGER_URL]: " MANAGER_URL_INPUT
MANAGER_URL=${MANAGER_URL_INPUT:-$DEFAULT_MANAGER_URL}
echo
print_info "Using settings:"
echo "Bot Directory: $BOT_DIR"
echo "Manager Self-Update URL: $MANAGER_URL"
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

# --- Writing the coka script content (Simplified Worker-Only Version) ---
cat > "$COKA_SCRIPT_PATH" << EOF
#!/bin/bash
VERSION="5.0 (Worker-Only Control Panel)"
BOT_DIR="$BOT_DIR"
MANAGER_SCRIPT_URL="$MANAGER_URL"
WORKER_SCREEN_NAME="worker_session"
print_info() { echo -e "\e[34mINFO: \$1\e[0m"; }
print_success() { echo -e "\e[32mSUCCESS: \$1\e[0m"; }
print_error() { echo -e "\e[31mERROR: \$1\e[0m"; }
print_warning() { echo -e "\e[33mWARNING: \$1\e[0m"; }
is_worker_running() { screen -list | grep -q "\$WORKER_SCREEN_NAME"; }
cd "\$BOT_DIR" || { print_error "Directory not found: \$BOT_DIR"; exit 1; }
case "\$1" in
    start)
        print_info "Ensuring worker is started..."
        if is_worker_running; then
            print_warning "Worker is already running. Restarting it..."
            screen -S "\$WORKER_SCREEN_NAME" -X quit
            sleep 2
        fi
        screen -dmS "\$WORKER_SCREEN_NAME" bash -c "source venv/bin/activate && python advanced_worker.py"
        sleep 2
        if is_worker_running; then print_success "Worker is now running."; else print_error "Failed to start worker."; fi
        ;;
    stop)
        print_info "Attempting to stop the worker..."
        if ! is_worker_running; then print_error "Worker is not running."; exit 1; fi
        screen -S "\$WORKER_SCREEN_NAME" -X quit
        print_success "Stop command sent to the worker."
        ;;
    restart)
        print_info "Restarting the worker..."
        coka stop
        sleep 2
        coka start
        ;;
    logs)
        case "\$2" in
            file) tail -f bot.log;;
            live) screen -r "\$WORKER_SCREEN_NAME";;
            *) print_error "Usage: coka logs [file|live]";;
        esac
        ;;
    update)
        print_info "Updating 'coka' manager script itself..."
        curl -s -L "\$MANAGER_SCRIPT_URL" | sudo bash
        if [ \$? -eq 0 ]; then
            print_success "'coka' manager has been updated successfully!"
        else
            print_error "Failed to download or run update script from GitHub."
        fi
        ;;
    status|*|"")
        SERVER_IP=\$(hostname -I | awk '{print \$1}')
        echo -e "\e[1;35m
    ╔════════════════════════════════════════════════════╗
    ║             COKA WORKER CONTROL PANEL              ║
    ╚════════════════════════════════════════════════════╝\e[0m"
        echo
        echo -e "  \e[1mServer IP:\e[0m \e[33m\$SERVER_IP\e[0m"
        echo -e "  \e[1mManager Version:\e[0m \e[36mv\$VERSION\e[0m"
        if is_worker_running; then STATUS_TEXT="\e[1;32mRUNNING\e[0m"; else STATUS_TEXT="\e[1;31mSTOPPED\e[0m"; fi
        echo -e "  \e[1mWorker Status:\e[0m \$STATUS_TEXT"
        echo
        echo -e "\e[2m------------------- Commands -----------------------------\e[0m"
        echo "  coka start         - Start/Restart the worker"
        echo "  coka stop          - Stop the worker"
        echo "  coka restart       - Restart the worker"
        echo "  coka logs [file|live] - View logs"
        echo "  coka update        - Update this management script"
        echo -e "\e[2m----------------------------------------------------------\e[0m"
        ;;
esac
EOF

# --- Final Step: Make it executable ---
chmod +x "$COKA_SCRIPT_PATH"
print_success "Management script 'coka' (v5.0) installed successfully!"
echo
print_info "You can now manage your worker by typing 'coka' from anywhere on the server."
echo
coka
