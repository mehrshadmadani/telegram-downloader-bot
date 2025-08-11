#!/bin/bash
# =============================================================
#         Coka Bot - Universal Management Script
# =============================================================

# --- Tanzimat (Settings) ---
VERSION="10.0 (Final Panel)"
# !!! MOHEM !!! Lotfan in 2 masir ra check konid.
# 1. Masir-e kamel-e poosheh-ye robot
BOT_DIR="/root/telegram-downloader-bot"
# 2. Link-e mostaghim be file-e install.sh dar GitHub (Raw Link)
MANAGER_SCRIPT_URL="https://raw.githubusercontent.com/mehrshadmadani/telegram-downloader-bot/main/install_coka.sh"

# Nam-e session-haye screen
WORKER_SCREEN_NAME="worker_session"
MAIN_BOT_SCREEN_NAME="main_bot_session"

# --- Functions ---
print_info() { echo -e "\e[34mINFO: \$1\e[0m"; }
print_success() { echo -e "\e[32mSUCCESS: \$1\e[0m"; }
print_error() { echo -e "\e[31mERROR: \$1\e[0m"; }
print_warning() { echo -e "\e[33mWARNING: \$1\e[0m"; }
is_running() { screen -list | grep -q "\$1"; }

# --- Core Logic Functions ---
start_service() {
    local service_name=\$1
    local screen_name=\$2
    local script_name=\$3
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
    local service_name=\$1
    local screen_name=\$2
    print_info "Attempting to stop \$service_name..."
    if ! is_running "\$screen_name"; then print_error "\$service_name is not running."; return; fi
    screen -S "\$screen_name" -X quit
    print_success "Stop command sent to \$service_name."
}

update_manager() {
    print_info "Updating 'coka' manager script itself..."
    # This command downloads and runs the installer, which will intelligently update coka
    curl -s -L "\$MANAGER_SCRIPT_URL" | sudo bash
    if [ \$? -eq 0 ]; then
        print_success "'coka' manager has been updated successfully!"
        print_info "Please run 'coka' again to use the new version."
    else
        print_error "Failed to download or run update script from GitHub."
    fi
}

# --- UI Functions ---
show_panel() {
    clear
    SERVER_IP=\$(hostname -I | awk '{print \$1}')
    echo -e "\e[1;35m
╔════════════════════════════════════════════════════╗
║             COKA BOT CONTROL PANEL                 ║
╚════════════════════════════════════════════════════╝\e[0m"
    echo -e "  \e[1mServer IP:\e[0m \e[33m\$SERVER_IP\e[0m  \e[1mManager:\e[0m \e[36mv\$VERSION\e[0m"
    if is_running "\$WORKER_SCREEN_NAME"; then W_STATUS="\e[1;32mRUNNING\e[0m"; else W_STATUS="\e[1;31mSTOPPED\e[0m"; fi
    if is_running "\$MAIN_BOT_SCREEN_NAME"; then M_STATUS="\e[1;32mRUNNING\e[0m"; else M_STATUS="\e[1;31mSTOPPED\e[0m"; fi
    echo -e "  \e[1mWorker Status:\e[0m \$W_STATUS   \e[1mMain Bot Status:\e[0m \$M_STATUS"
    echo -e "\e[2m----------------------------------------------------------\e[0m"
}

worker_menu() {
    while true; do
        show_panel
        echo "  Worker Manager Menu:"
        echo "  [1] Start / Restart Worker"
        echo "  [2] Stop Worker"
        echo "  [3] View Live Dashboard (Dashbord-e Zendeh)"
        echo "  [4] View Log File (Log-e Fanni)"
        echo "  [5] Back to Main Menu (Bazgasht)"
        echo -e "\e[2m----------------------------------------------------------\e[0m"
        read -p "  Enter your choice: " choice
        case \$choice in
            1) start_service "Worker" "\$WORKER_SCREEN_NAME" "advanced_worker.py" ;;
            2) stop_service "Worker" "\$WORKER_SCREEN_NAME" ;;
            3) print_warning "To detach, press Ctrl+A then D."; sleep 2; screen -r "\$WORKER_SCREEN_NAME" ;;
            4) tail -f bot.log ;;
            5) return ;;
            *) print_error "Invalid option." ;;
        esac
        echo; read -p "Press [Enter] to continue..."
    done
}

main_bot_menu() {
    while true; do
        show_panel
        echo "  Main Bot Manager Menu:"
        echo "  [1] Start / Restart Main Bot"
        echo "  [2] Stop Main Bot"
        echo "  [3] View Log File"
        echo "  [4] Back to Main Menu (Bazgasht)"
        echo -e "\e[2m----------------------------------------------------------\e[0m"
        read -p "  Enter your choice: " choice
        case \$choice in
            1) start_service "Main Bot" "\$MAIN_BOT_SCREEN_NAME" "main_bot.py" ;;
            2) stop_service "Main Bot" "\$MAIN_BOT_SCREEN_NAME" ;;
            3) tail -f main_bot.log ;;
            4) return ;;
            *) print_error "Invalid option." ;;
        esac
        echo; read -p "Press [Enter] to continue..."
    done
}

main_menu() {
    while true; do
        show_panel
        echo "  Main Menu:"
        echo "  [1] Worker Manager"
        echo "  [2] Main Bot Manager"
        echo "  [3] Update This Manager (coka)"
        echo "  [q] Quit (Khorooj)"
        echo -e "\e[2m----------------------------------------------------------\e[0m"
        read -p "  Enter your choice: " choice
        case \$choice in
            1) worker_menu ;;
            2) main_bot_menu ;;
            3) update_manager; exit 0 ;;
            q|Q) echo "Exiting."; exit 0 ;;
            *) print_error "Invalid option." ;;
        esac
    done
}

# --- Main Script ---
cd "\$BOT_DIR" || { print_error "Directory not found: \$BOT_DIR"; exit 1; }

# If arguments are provided, run in command mode
if [ -n "\$1" ]; then
    case "\$1" in
        start) start_service "\$2" "\${2}_session" "\${2}.py" ;;
        stop) stop_service "\$2" "\${2}_session" ;;
        restart) stop_service "\$2" "\${2}_session"; sleep 2; start_service "\$2" "\${2}_session" "\${2}.py" ;;
        status) show_panel ;;
        update) update_manager ;;
        *) print_error "Unknown command: \$1";;
    esac
    exit 0
fi

# If no arguments, run in interactive menu mode
main_menu
