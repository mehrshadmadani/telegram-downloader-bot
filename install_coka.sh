#!/bin/bash

# =============================================================
#         Coka Bot Manager - Universal Installer v25.0 (Hardcoded URLs)
# =============================================================

COKA_SCRIPT_PATH="/usr/local/bin/coka"
VERSION_URL="https://raw.githubusercontent.com/mehrshadmadani/telegram-downloader-bot/main/version.txt"

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

if [ -f "$COKA_SCRIPT_PATH" ]; then
    print_warning "'coka' command is already installed."
    LATEST_VERSION=$(curl -sL "$VERSION_URL" | head -n 1)
    if [ -z "$LATEST_VERSION" ]; then LATEST_VERSION="N/A"; fi
    
    read -p "Do you want to force overwrite it with the latest version from GitHub (v$LATEST_VERSION)? (y/n): " OVERWRITE_CONFIRM
    if [[ "$OVERWRITE_CONFIRM" != "y" ]]; then
        print_info "Installation cancelled."
        exit 0
    fi
else
    LATEST_VERSION=$(curl -sL "$VERSION_URL" | head -n 1)
    if [ -z "$LATEST_VERSION" ]; then LATEST_VERSION="25.0 (Hardcoded)"; fi
fi

# --- Installation ---
print_info "Installing required utilities (screen, curl, bc)..."
apt-get update > /dev/null 2>&1
apt-get install -y screen curl bc > /dev/null 2>&1
print_info "Creating the 'coka' management script..."

# --- Writing the coka script content ---
cat > "$COKA_SCRIPT_PATH" << EOF
#!/bin/bash
VERSION="$LATEST_VERSION"

# --- Tanzimat (Settings) ---
BOT_DIR="/root/telegram-downloader-bot"
WORKER_SCREEN_NAME="worker_session"
MAIN_BOT_SCREEN_NAME="main_bot_session"

# --- Link-haye Sabet baraye Update (Hardcoded URLs) ---
MANAGER_SCRIPT_URL="https://raw.githubusercontent.com/mehrshadmadani/telegram-downloader-bot/main/install_coka.sh"
WORKER_SCRIPT_URL="https://raw.githubusercontent.com/mehrshadmadani/telegram-downloader-bot/main/advanced_worker.py"
MAIN_BOT_SCRIPT_URL="https://raw.githubusercontent.com/mehrshadmadani/telegram-downloader-bot/main/main_bot.py"


# --- Functions ---
print_info() { echo -e "\e[34mINFO: \$1\e[0m"; }
print_success() { echo -e "\e[32mSUCCESS: \$1\e[0m"; }
print_error() { echo -e "\e[31mERROR: \$1\e[0m"; }
print_warning() { echo -e "\e[33mWARNING: \$1\e[0m"; }
is_running() { screen -list | grep -q "\$1"; }

# --- Core Logic Functions ---
start_service() {
    local service_name=\$1; local screen_name=\$2; local script_name=\$3
    print_info "Ensuring \$service_name is started..."
    if is_running "\$screen_name"; then
        print_warning "\$service_name is already running. Restarting it..."
        screen -S "\$screen_name" -X quit; sleep 2
    fi
    screen -dmS "\$screen_name" bash -c "source venv/bin/activate && python \$script_name"
    sleep 2
    if is_running "\$screen_name"; then print_success "\$service_name is now running."; else print_error "Failed to start \$service_name."; fi
}

stop_service() {
    local service_name=\$1; local screen_name=\$2
    print_info "Attempting to stop \$service_name..."
    if ! is_running "\$screen_name"; then print_error "\$service_name is not running."; return; fi
    screen -S "\$screen_name" -X quit
    print_success "Stop command sent to \$service_name."
}

update_script() {
    local service_name=\$1
    local script_url=\$2
    local file_path=\$3
    
    print_warning "This will overwrite '\$file_path' with the latest version from GitHub."
    read -p "Are you sure? (y/n): " confirm
    if [[ "\$confirm" != "y" ]]; then
        print_info "Update for \$service_name cancelled."
        return
    fi
    
    print_info "Updating \$service_name script..."
    curl -s -L "\$script_url" -o "\$file_path"
    if [ \$? -eq 0 ]; then
        print_success "\$service_name script updated successfully."
        print_warning "Restart the service to apply changes: 'coka restart \$service_name'"
    else
        print_error "Failed to download update for \$service_name."
    fi
}

update_manager() {
    print_warning "This will update the 'coka' script to the latest version from GitHub."
    read -p "Are you sure you want to continue? (y/n): " UPDATE_CONFIRM
    if [[ "\$UPDATE_CONFIRM" != "y" ]]; then
        print_info "Update cancelled."
        return
    fi
    print_info "Updating 'coka' manager script itself..."
    curl -s -L "\$MANAGER_SCRIPT_URL" | sudo bash
    if [ \$? -eq 0 ]; then
        print_success "'coka' manager has been updated successfully!"
        print_info "Relaunching..."
        sleep 2
        exec coka
    else
        print_error "Failed to run update script.";
    fi
}

# --- UI Functions ---
show_panel_and_menu() {
    clear
    SERVER_IP=\$(hostname -I | cut -d' ' -f1)
    CPU_USAGE=\$(top -bn1 | grep "Cpu(s)" | sed "s/.*, *\([0-9.]*\)%* id.*/\1/" | awk '{print 100 - \$1"%%"}')
    MEM_INFO=\$(free -m | awk 'NR==2{printf "%.2f/%.2f GB (%.0f%%)", \$3/1024, \$2/1024, \$3*100/\$2 }')
    DISK_INFO=\$(df -h / | awk 'NR==2{printf "%s / %s (%s)", \$3, \$2, \$5}')
    if is_running "\$WORKER_SCREEN_NAME"; then W_STATUS="\e[1;32mRUNNING\e[0m"; else W_STATUS="\e[1;31mSTOPPED\e[0m"; fi
    if is_running "\$MAIN_BOT_SCREEN_NAME"; then M_STATUS="\e[1;32mRUNNING\e[0m"; else M_STATUS="\e[1;31mSTOPPED\e[0m"; fi

    echo -e "\e[1;35m
╔═════════════════════════════════════════════════════════════════════════════╗
║                          COKA BOT CONTROL PANEL                             ║
╚═════════════════════════════════════════════════════════════════════════════╝\e[0m"
    echo -e "  \e[1mCPU:\e[0m \e[1;37m\$CPU_USAGE \e[1m| RAM:\e[0m \e[1;37m\$MEM_INFO \e[1m| Disk:\e[0m \e[1;37m\$DISK_INFO"
    echo -e "\e[2m-------------------------------------------------------------------------------\e[0m"
    echo -e "  \e[1mServer IP:\e[0m \e[33m\$SERVER_IP\e[0m  \e[1mManager:\e[0m \e[36mv\$VERSION\e[0m"
    echo -e "  \e[1mWorker Status:\e[0m \$W_STATUS   \e[1mMain Bot Status:\e[0m \$M_STATUS"
    echo -e "\e[2m-------------------------------------------------------------------------------\e[0m"
}

worker_menu() {
    while true; do
        show_panel_and_menu
        echo "  Worker Manager Menu:"
        echo "  [1] Start / Restart"
        echo "  [2] Stop"
        echo "  [3] View Live Dashboard"
        echo "  [4] View Log File"
        echo "  [5] Update from GitHub"
        echo "  [0] Back to Main Menu"
        echo -e "\e[2m-------------------------------------------------------------------------------\e[0m"
        read -p "  Enter your choice: " choice
        case \$choice in
            1) start_service "worker" "\$WORKER_SCREEN_NAME" "advanced_worker.py";;
            2) stop_service "worker" "\$WORKER_SCREEN_NAME" ;;
            3) screen -r "\$WORKER_SCREEN_NAME" ;;
            4) tail -f bot.log ;;
            5) update_script "worker" "\$WORKER_SCRIPT_URL" "\$BOT_DIR/advanced_worker.py" ;;
            0) return ;;
            *) print_error "Invalid option." ;;
        esac
        echo; read -p "Press [Enter] to continue..."
    done
}

main_bot_menu() {
     while true; do
        show_panel_and_menu
        echo "  Main Bot Manager Menu:"
        echo "  [1] Start / Restart"
        echo "  [2] Stop"
        echo "  [3] View Log File"
        echo "  [4] Update from GitHub"
        echo "  [0] Back to Main Menu"
        echo -e "\e[2m-------------------------------------------------------------------------------\e[0m"
        read -p "  Enter your choice: " choice
        case \$choice in
            1) start_service "main" "\$MAIN_BOT_SCREEN_NAME" "main_bot.py" ;;
            2) stop_service "main" "\$MAIN_BOT_SCREEN_NAME" ;;
            3) tail -f main_bot.log ;;
            4) update_script "main" "\$MAIN_BOT_SCRIPT_URL" "\$BOT_DIR/main_bot.py" ;;
            0) return ;;
            *) print_error "Invalid option." ;;
        esac
        echo; read -p "Press [Enter] to continue..."
    done
}

main_menu() {
    while true; do
        show_panel_and_menu
        echo "  Main Menu:"
        echo "  [1] Worker Manager"
        echo "  [2] Main Bot Manager"
        echo "  [3] Update This Manager (coka)"
        echo "  [0] Quit"
        echo -e "\e[2m-------------------------------------------------------------------------------\e[0m"
        read -p "  Enter your choice: " choice
        case \$choice in
            1) worker_menu ;;
            2) main_bot_menu ;;
            3) update_manager; ;;
            0) echo "Exiting."; clear; exit 0 ;;
            *) print_error "Invalid option." ;;
        esac
    done
}

cd "\$BOT_DIR" || { print_error "Directory not found: \$BOT_DIR"; exit 1; }
main_menu
EOF

# --- Final Step: Make it executable ---
chmod +x "$COKA_SCRIPT_PATH"
print_success "Management script 'coka' (v$LATEST_VERSION) installed successfully!"
echo
coka
