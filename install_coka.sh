#!/bin/bash

# =============================================================
#         Coka Bot Manager - Universal Smart Installer v14.0 (Full Monitoring)
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

DEFAULT_BOT_DIR="/root/telegram-downloader-bot"
DEFAULT_MANAGER_URL="https://raw.githubusercontent.com/mehrshadmadani/telegram-downloader-bot/main/install_coka.sh"

if [ -f "$COKA_SCRIPT_PATH" ]; then
    print_warning "'coka' command is already installed."
    EXISTING_BOT_DIR=$(grep -oP 'BOT_DIR="\K[^"]+' "$COKA_SCRIPT_PATH" || echo "$DEFAULT_BOT_DIR")
    EXISTING_MANAGER_URL=$(grep -oP 'MANAGER_SCRIPT_URL="\K[^"]+' "$COKA_SCRIPT_PATH" || echo "$DEFAULT_MANAGER_URL")
    DEFAULT_BOT_DIR=$EXISTING_BOT_DIR
    DEFAULT_MANAGER_URL=$EXISTING_MANAGER_URL
    read -p "Do you want to force overwrite it with the latest version (v14.0)? (y/n): " OVERWRITE_CONFIRM
    if [[ "$OVERWRITE_CONFIRM" != "y" ]]; then
        print_info "Installation cancelled."
        exit 0
    fi
fi

# --- Interactive Setup ---
print_info "Configuring the 'coka' management command..."
read -p "Enter the full path to your bot directory [Default: $DEFAULT_BOT_DIR]: " BOT_DIR_INPUT
BOT_DIR=${BOT_DIR_INPUT:-$DEFAULT_BOT_DIR}
read -p "Enter the raw GitHub URL for this installer script itself [Default: $DEFAULT_MANAGER_URL]: " MANAGER_URL_INPUT
MANAGER_URL=${MANAGER_URL_INPUT:-$DEFAULT_MANAGER_URL}

# --- Installation ---
print_info "Installing required utilities (screen, curl)..."
apt-get update > /dev/null 2>&1
apt-get install -y screen curl > /dev/null 2>&1
print_info "Creating the 'coka' management script..."

# --- Writing the coka script content ---
cat > "$COKA_SCRIPT_PATH" << EOF
#!/bin/bash
VERSION="14.0 (Live Monitoring)"
BOT_DIR="$BOT_DIR"
MANAGER_SCRIPT_URL="$MANAGER_URL"
WORKER_SCREEN_NAME="worker_session"
MAIN_BOT_SCREEN_NAME="main_bot_session"

print_info() { echo -e "\e[34mINFO: \$1\e[0m"; }
print_success() { echo -e "\e[32mSUCCESS: \$1\e[0m"; }
print_error() { echo -e "\e[31mERROR: \$1\e[0m"; }
print_warning() { echo -e "\e[33mWARNING: \$1\e[0m"; }
is_running() { screen -list | grep -q "\$1"; }

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

update_manager() {
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

format_speed() {
    local speed=\$1
    if (( \$(echo "\$speed > 1024*1024" | bc -l) )); then
        printf "%.2f MB/s" \$(echo "scale=2; \$speed / (1024*1024)" | bc)
    elif (( \$(echo "\$speed > 1024" | bc -l) )); then
        printf "%.2f KB/s" \$(echo "scale=2; \$speed / 1024" | bc)
    else
        printf "%d B/s" \$speed
    fi
}

show_panel() {
    clear
    # System Info
    SERVER_IP=\$(hostname -I | cut -d' ' -f1)
    CPU_USAGE=\$(top -bn1 | grep "Cpu(s)" | sed "s/.*, *\([0-9.]*\)%* id.*/\1/" | awk '{print 100 - \$1"%%"}')
    MEM_INFO=\$(free -m | awk 'NR==2{printf "%.2f/%.2f GB (%.0f%%)", \$3/1024, \$2/1024, \$3*100/\$2 }')
    DISK_INFO=\$(df -h / | awk 'NR==2{printf "%s / %s (%s)", \$3, \$2, \$5}')
    
    # Network Info
    INTERFACE=\$(ip route | grep default | awk '{print \$5}' | head -1)
    RX_BYTES_1=\$(cat /sys/class/net/\$INTERFACE/statistics/rx_bytes)
    TX_BYTES_1=\$(cat /sys/class/net/\$INTERFACE/statistics/tx_bytes)
    sleep 1
    RX_BYTES_2=\$(cat /sys/class/net/\$INTERFACE/statistics/rx_bytes)
    TX_BYTES_2=\$(cat /sys/class/net/\$INTERFACE/statistics/tx_bytes)
    RX_SPEED=\$((RX_BYTES_2 - RX_BYTES_1))
    TX_SPEED=\$((TX_BYTES_2 - TX_BYTES_1))
    RX_FORMATTED=\$(format_speed \$RX_SPEED)
    TX_FORMATTED=\$(format_speed \$TX_SPEED)

    echo -e "\e[1;35m
╔═════════════════════════════════════════════════════════════════════════════╗
║                          COKA BOT CONTROL PANEL                             ║
╚═════════════════════════════════════════════════════════════════════════════╝\e[0m"
    echo -e "  \e[1mCPU:\e[0m \e[1;37m\$CPU_USAGE \e[1m| RAM:\e[0m \e[1;37m\$MEM_INFO \e[1m| Disk:\e[0m \e[1;37m\$DISK_INFO"
    echo -e "  \e[1mNetwork (\${INTERFACE}):\e[0m \e[1;37m↓ \$RX_FORMATTED | ↑ \$TX_FORMATTED"
    echo -e "\e[2m-------------------------------------------------------------------------------\e[0m"
    echo -e "  \e[1mServer IP:\e[0m \e[33m\$SERVER_IP\e[0m  \e[1mManager:\e[0m \e[36mv\$VERSION\e[0m"
    if is_running "\$WORKER_SCREEN_NAME"; then W_STATUS="\e[1;32mRUNNING\e[0m"; else W_STATUS="\e[1;31mSTOPPED\e[0m"; fi
    if is_running "\$MAIN_BOT_SCREEN_NAME"; then M_STATUS="\e[1;32mRUNNING\e[0m"; else M_STATUS="\e[1;31mSTOPPED\e[0m"; fi
    echo -e "  \e[1mWorker Status:\e[0m \$W_STATUS   \e[1mMain Bot Status:\e[0m \$M_STATUS"
    echo -e "\e[2m-------------------------------------------------------------------------------\e[0m"
}

worker_menu() {
    while true; do
        show_panel
        echo "  Worker Manager Menu:"
        echo "  [1] Start / Restart Worker"
        echo "  [2] Stop Worker"
        echo "  [3] View Live Dashboard"
        echo "  [4] View Log File"
        echo "  [0] Back to Main Menu"
        echo -e "\e[2m-------------------------------------------------------------------------------\e[0m"
        read -t 2 -N 1 -p "  Enter your choice (refreshes automatically): " choice
        if [ -z "\$choice" ]; then continue; fi
        case \$choice in
            1) start_service "Worker" "\$WORKER_SCREEN_NAME" "advanced_worker.py"; echo; read -p "Press [Enter]...";;
            2) stop_service "Worker" "\$WORKER_SCREEN_NAME"; echo; read -p "Press [Enter]...";;
            3) print_warning "To detach, press Ctrl+A then D."; sleep 2; screen -r "\$WORKER_SCREEN_NAME" ;;
            4) tail -f bot.log ;;
            0) return ;;
        esac
    done
}

main_bot_menu() {
     while true; do
        show_panel
        echo "  Main Bot Manager Menu:"
        echo "  [1] Start / Restart Main Bot"
        echo "  [2] Stop Main Bot"
        echo "  [3] View Log File"
        echo "  [0] Back to Main Menu"
        echo -e "\e[2m-------------------------------------------------------------------------------\e[0m"
        read -t 2 -N 1 -p "  Enter your choice (refreshes automatically): " choice
        if [ -z "\$choice" ]; then continue; fi
        case \$choice in
            1) start_service "Main Bot" "\$MAIN_BOT_SCREEN_NAME" "main_bot.py"; echo; read -p "Press [Enter]...";;
            2) stop_service "Main Bot" "\$MAIN_BOT_SCREEN_NAME"; echo; read -p "Press [Enter]...";;
            3) tail -f main_bot.log ;;
            0) return ;;
        esac
    done
}

main_menu() {
    while true; do
        show_panel
        echo "  Main Menu:"
        echo "  [1] Worker Manager"
        echo "  [2] Main Bot Manager"
        echo "  [3] Update This Manager (coka)"
        echo "  [0] Quit"
        echo -e "\e[2m-------------------------------------------------------------------------------\e[0m"
        read -t 2 -N 1 -p "  Enter your choice (refreshes automatically): " choice
        if [ -z "\$choice" ]; then continue; fi
        case \$choice in
            1) worker_menu ;;
            2) main_bot_menu ;;
            3) update_manager; exit 0 ;;
            0) echo "Exiting."; exit 0 ;;
        esac
    done
}

# --- Main Script ---
cd "\$BOT_DIR" || { print_error "Directory not found: \$BOT_DIR"; exit 1; }
main_menu
EOF

# --- Final Step: Make it executable ---
chmod +x "$COKA_SCRIPT_PATH"
print_success "Management script 'coka' (v14.0) installed successfully!"
echo
coka
