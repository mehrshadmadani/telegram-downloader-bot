#!/bin/bash

# =============================================================
#         Coka Bot Manager - Universal Smart Installer v8.0
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
    read -p "Do you want to force overwrite it with the latest version (v8.0 with auto-cleanup)? (y/n): " OVERWRITE_CONFIRM
    if [[ "$OVERWRITE_CONFIRM" != "y" ]]; then
        print_info "Installation cancelled."
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

# --- Installation ---
print_info "Installing required utilities (screen, curl)..."
apt-get update > /dev/null 2>&1
apt-get install -y screen curl > /dev/null 2>&1
print_success "Utilities are ready."
print_info "Creating the 'coka' management script with your settings..."

# --- Writing the coka script content (Auto-Cleanup Version) ---
cat > "$COKA_SCRIPT_PATH" << EOF
#!/bin/bash
VERSION="8.0 (Auto-Cleanup)"
BOT_DIR="$BOT_DIR"
MANAGER_SCRIPT_URL="$MANAGER_URL"
WORKER_SCREEN_NAME="worker_session"
print_info() { echo -e "\e[34mINFO: \$1\e[0m"; }
print_success() { echo -e "\e[32mSUCCESS: \$1\e[0m"; }
print_error() { echo -e "\e[31mERROR: \$1\e[0m"; }
print_warning() { echo -e "\e[33mWARNING: \$1\e[0m"; }
is_worker_running() { screen -list | grep -q "\$WORKER_SCREEN_NAME"; }

# --- Core Logic Functions ---
start_worker() {
    print_info "Starting worker with auto-cleanup..."
    
    # Step 1: Forcefully kill any lingering python processes for the worker
    print_info "--> Stopping any orphaned worker processes..."
    pkill -f "python advanced_worker.py"
    sleep 1

    # Step 2: Clean up any dead screen sessions
    print_info "--> Wiping dead screen sessions..."
    screen -wipe > /dev/null 2>&1
    
    # Step 3: Start the new, clean session
    print_info "--> Starting a new worker session..."
    screen -dmS "\$WORKER_SCREEN_NAME" bash -c "source venv/bin/activate && python advanced_worker.py"
    sleep 2

    if is_worker_running; then
        print_success "Worker is now running cleanly in the background."
        print_info "Use 'coka logs live' to see the dashboard."
    else
        print_error "Failed to start worker after cleanup. Please check logs."
    fi
}
stop_worker() {
    print_info "Attempting to stop the worker..."
    # Using pkill is more reliable than just quitting the screen
    pkill -f "python advanced_worker.py"
    screen -wipe > /dev/null 2>&1
    sleep 1
    if is_worker_running; then
        screen -S "\$WORKER_SCREEN_NAME" -X quit
        print_warning "Screen session was still alive, sent final quit command."
    fi
    print_success "Worker process stopped successfully."
}
update_manager() {
    print_info "Updating 'coka' manager script itself..."
    curl -s -L "\$MANAGER_SCRIPT_URL" | sudo bash
    if [ \$? -eq 0 ]; then
        print_success "'coka' manager has been updated successfully!"
    else
        print_error "Failed to download or run manager update script."
    fi
}
show_status_panel() {
    SERVER_IP=\$(hostname -I | awk '{print \$1}')
    echo -e "\e[1;35m
╔════════════════════════════════════════════════════╗
║             COKA WORKER CONTROL PANEL              ║
╚════════════════════════════════════════════════════╝\e[0m"
    echo -e "  \e[1mServer IP:\e[0m \e[33m\$SERVER_IP\e[0m"
    echo -e "  \e[1mManager Version:\e[0m \e[36mv\$VERSION\e[0m"
    if is_worker_running; then STATUS_TEXT="\e[1;32mRUNNING\e[0m"; else STATUS_TEXT="\e[1;31mSTOPPED\e[0m"; fi
    echo -e "  \e[1mWorker Status:\e[0m \$STATUS_TEXT"
    echo -e "\e[2m----------------------------------------------------------\e[0m"
}

# --- Main Script ---
cd "\$BOT_DIR" || { print_error "Directory not found: \$BOT_DIR"; exit 1; }
case "\$1" in
    start) start_worker ;;
    stop) stop_worker ;;
    restart) start_worker ;; # Restart is now the same as start
    logs)
        case "\$2" in
            file) tail -f bot.log;;
            live) screen -r "\$WORKER_SCREEN_NAME";;
            *) print_error "Usage: coka logs [file|live]";;
        esac
        ;;
    update) update_manager ;;
    status|*|"")
        show_status_panel
        echo
        echo "Dastoorat-e Mojood (Available commands):"
        echo "  coka start         - Start/Restart kardan-e worker (ba pak-sazi-e ghabli)"
        echo "  coka stop          - Stop kardan-e worker"
        echo "  coka logs [file|live] - Namayesh-e log-ha"
        echo "  coka update        - Update kardan-e hamin script (coka)"
        ;;
esac
EOF

# --- Final Step: Make it executable ---
chmod +x "$COKA_SCRIPT_PATH"

print_success "Management script 'coka' (v8.0) installed successfully!"
echo
coka
