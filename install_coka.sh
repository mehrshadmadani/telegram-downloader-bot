#!/bin/bash

# =============================================================
#         Coka Bot Manager - Universal Smart Installer v7.0
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
    read -p "Do you want to force overwrite it with the latest version (v7.0)? (y/n): " OVERWRITE_CONFIRM
    if [[ "$OVERWRITE_CONFIRM" != "y" ]]; then
        print_info "Installation cancelled. Showing current status:"
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

DEFAULT_WORKER_URL="https://raw.githubusercontent.com/mehrshadmadani/telegram-downloader-bot/main/advanced_worker.py"
read -p "Enter the raw GitHub URL for advanced_worker.py [Default: $DEFAULT_WORKER_URL]: " WORKER_URL_INPUT
WORKER_URL=${WORKER_URL_INPUT:-$DEFAULT_WORKER_URL}

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

# --- Writing the coka script content (Interactive Menu Version with separate updates) ---
cat > "$COKA_SCRIPT_PATH" << EOF
#!/bin/bash
VERSION="7.0 (Separate Updates)"
BOT_DIR="$BOT_DIR"
WORKER_GITHUB_URL="$WORKER_URL"
MANAGER_SCRIPT_URL="$MANAGER_URL"
WORKER_SCREEN_NAME="worker_session"
print_info() { echo -e "\e[34mINFO: \$1\e[0m"; }
print_success() { echo -e "\e[32mSUCCESS: \$1\e[0m"; }
print_error() { echo -e "\e[31mERROR: \$1\e[0m"; }
print_warning() { echo -e "\e[33mWARNING: \$1\e[0m"; }
is_worker_running() { screen -list | grep -q "\$WORKER_SCREEN_NAME"; }

# --- Core Logic Functions ---
start_worker() {
    print_info "Ensuring worker is started..."
    if is_worker_running; then
        print_warning "Worker is already running. Restarting it..."
        screen -S "\$WORKER_SCREEN_NAME" -X quit; sleep 2
    fi
    screen -dmS "\$WORKER_SCREEN_NAME" bash -c "source venv/bin/activate && python advanced_worker.py"
    sleep 2
    if is_worker_running; then print_success "Worker is now running."; else print_error "Failed to start worker."; fi
}
stop_worker() {
    print_info "Attempting to stop the worker..."
    if ! is_worker_running; then print_error "Worker is not running."; exit 1; fi
    screen -S "\$WORKER_SCREEN_NAME" -X quit
    print_success "Stop command sent to the worker."
}
update_worker_script() {
    print_info "Updating worker script (advanced_worker.py) from GitHub..."
    curl -s -L "\$WORKER_GITHUB_URL" -o "\${BOT_DIR}/advanced_worker.py"
    if [ \$? -eq 0 ]; then
        print_success "Worker script updated successfully."
        print_warning "Baraye e'mal-e taghirat, worker ra restart kon: 'coka restart'"
    else
        print_error "Failed to download worker update from GitHub."
    fi
}
update_manager_script() {
    print_info "Updating 'coka' manager script itself..."
    curl -s -L "\$MANAGER_SCRIPT_URL" | sudo bash
    if [ \$? -eq 0 ]; then
        print_success "'coka' manager has been updated successfully!"
        print_info "Please run 'coka' again to use the new version."
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
show_menu() {
    show_status_panel
    echo "  [1] Start / Restart Worker"
    echo "  [2] Stop Worker"
    echo "  [3] View Live Dashboard (Dashbord-e Zendeh)"
    echo "  [4] View Log File (Log-e Fanni)"
    echo "  [5] Update Worker Script (Update Kardan-e Worker)"
    echo "  [6] Update Manager (Update Kardan-e Coka)"
    echo "  [q] Quit (Khorooj)"
    echo -e "\e[2m----------------------------------------------------------\e[0m"
}

# --- Main Script ---
cd "\$BOT_DIR" || { print_error "Directory not found: \$BOT_DIR"; exit 1; }
if [ -z "\$1" ]; then
    while true; do
        clear
        show_menu
        read -p "  Enter your choice (1-6, q): " choice
        case \$choice in
            1) start_worker ;;
            2) stop_worker ;;
            3) screen -r "\$WORKER_SCREEN_NAME" ;;
            4) tail -f bot.log ;;
            5) update_worker_script ;;
            6) update_manager_script; exit 0 ;;
            q|Q) echo "Exiting."; exit 0 ;;
            *) print_error "Invalid option." ;;
        esac
        echo; read -p "Press [Enter] to return to the menu..."
    done
else
    case "\$1" in
        start) start_worker ;;
        stop) stop_worker ;;
        restart) stop_worker; sleep 2; start_worker ;;
        update-worker) update_worker_script ;;
        update) update_manager_script ;;
        *) print_error "Unknown command: \$1";;
    esac
    exit 0
fi
EOF

# --- Final Step: Make it executable ---
chmod +x "$COKA_SCRIPT_PATH"
print_success "Management script 'coka' (v7.0) installed successfully!"
echo
coka
