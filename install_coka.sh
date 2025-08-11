#!/bin/bash

# =============================================================
#         Coka Bot Manager - Universal Smart Installer v4.0
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

# 1. Ask for the bot directory path
DEFAULT_BOT_DIR="/root/telegram-downloader-bot"
read -p "Enter the full path to your bot directory [Default: $DEFAULT_BOT_DIR]: " BOT_DIR_INPUT
BOT_DIR=${BOT_DIR_INPUT:-$DEFAULT_BOT_DIR}

# 2. Ask for the coka script's own raw GitHub URL for self-updating
DEFAULT_MANAGER_URL="https://raw.githubusercontent.com/mehrshadmadani/telegram-downloader-bot/main/install_coka.sh"
read -p "Enter the raw GitHub URL for the coka installer script itself [Default: $DEFAULT_MANAGER_URL]: " MANAGER_URL_INPUT
MANAGER_URL=${MANAGER_URL_INPUT:-$DEFAULT_MANAGER_URL}

echo
print_info "Using the following settings:"
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

# --- Writing the coka script content (Control Panel Version) ---
cat > "$COKA_SCRIPT_PATH" << EOF
#!/bin/bash
# =============================================================
#         Coka Bot - Universal Management Script
# =============================================================
VERSION="4.0 (Control Panel)"
BOT_DIR="$BOT_DIR"
MANAGER_SCRIPT_URL="$MANAGER_URL"
WORKER_SCREEN_NAME="worker_session"
MAIN_BOT_SCREEN_NAME="main_bot_session"
print_info() { echo -e "\e[34mINFO: \$1\e[0m"; }
print_success() { echo -e "\e[32mSUCCESS: \$1\e[0m"; }
print_error() { echo -e "\e[31mERROR: \$1\e[0m"; }
print_warning() { echo -e "\e[33mWARNING: \$1\e[0m"; }
is_running() { screen -list | grep -q "\$1"; }
cd "\$BOT_DIR" || { print_error "Directory not found: \$BOT_DIR"; exit 1; }
case "\$1" in
    start)
        case "\$2" in
            worker)
                print_info "Ensuring worker is started..."
                if is_running "\$WORKER_SCREEN_NAME"; then
                    print_warning "Worker is already running. Restarting..."
                    screen -S "\$WORKER_SCREEN_NAME" -X quit
                    sleep 2
                fi
                screen -dmS "\$WORKER_SCREEN_NAME" bash -c "source venv/bin/activate && python advanced_worker.py"
                sleep 1
                if is_running "\$WORKER_SCREEN_NAME"; then print_success "Worker is now running."; else print_error "Failed to start worker."; fi;;
            main)
                print_info "Ensuring main bot is started..."
                if is_running "\$MAIN_BOT_SCREEN_NAME"; then
                    print_warning "Main bot is already running. Restarting..."
                    screen -S "\$MAIN_BOT_SCREEN_NAME" -X quit
                    sleep 2
                fi
                screen -dmS "\$MAIN_BOT_SCREEN_NAME" bash -c "source venv/bin/activate && python main_bot.py"
                sleep 1
                if is_running "\$MAIN_BOT_SCREEN_NAME"; then print_success "Main bot is now running."; else print_error "Failed to start main bot."; fi;;
            *) print_error "Usage: coka start [worker|main]";;
        esac;;
    stop)
        case "\$2" in
            worker)
                if ! is_running "\$WORKER_SCREEN_NAME"; then print_error "Worker is not running."; exit 1; fi
                screen -S "\$WORKER_SCREEN_NAME" -X quit
                print_success "Stop command sent to the worker.";;
            main)
                if ! is_running "\$MAIN_BOT_SCREEN_NAME"; then print_error "Main bot is not running."; exit 1; fi
                screen -S "\$MAIN_BOT_SCREEN_NAME" -X quit
                print_success "Stop command sent to the main bot.";;
            all)
                print_info "Attempting to stop all services..."
                screen -S "\$WORKER_SCREEN_NAME" -X quit
                screen -S "\$MAIN_BOT_SCREEN_NAME" -X quit
                print_success "Stop command sent to all services.";;
            *) print_error "Usage: coka stop [worker|main|all]";;
        esac;;
    restart) coka stop "\$2"; sleep 2; coka start "\$2";;
    status|'')
        SERVER_IP=\$(hostname -I | awk '{print \$1}')
        echo -e "\e[1;35m
    ╔════════════════════════════════════════════════════╗
    ║             COKA BOT CONTROL PANEL                 ║
    ╚════════════════════════════════════════════════════╝\e[0m"
        echo
        echo -e "  \e[1mServer IP:\e[0m \e[33m\$SERVER_IP\e[0m"
        echo -e "  \e[1mManager Version:\e[0m \e[36mv\$VERSION\e[0m"
        if is_running "\$WORKER_SCREEN_NAME"; then STATUS_TEXT="\e[1;32mRUNNING\e[0m"; else STATUS_TEXT="\e[1;31mSTOPPED\e[0m"; fi
        echo -e "  \e[1mWorker Status:\e[0m \$STATUS_TEXT"
        if is_running "\$MAIN_BOT_SCREEN_NAME"; then STATUS_TEXT="\e[1;32mRUNNING\e[0m"; else STATUS_TEXT="\e[1;31mSTOPPED\e[0m"; fi
        echo -e "  \e[1mMain Bot Status:\e[0m \$STATUS_TEXT"
        echo
        echo -e "\e[2m----------------------------------------------------------\e[0m";;
    logs)
        case "\$2" in
            worker) tail -f bot.log;;
            main) tail -f main_bot.log;;
            live) screen -r "\$WORKER_SCREEN_NAME";;
            *) print_error "Usage: coka logs [worker|main|live]";;
        esac;;
    update)
        print_info "Updating 'coka' manager script itself..."
        curl -s -L "\$MANAGER_SCRIPT_URL" | sudo bash
        if [ \$? -eq 0 ]; then
            print_success "'coka' manager has been updated successfully!"
            print_info "Please run 'coka' again to use the new version."
        else
            print_error "Failed to download or run update script from GitHub."
        fi;;
    *)
        coka status
        echo
        echo "Dastoorat-e Mojood (Available commands):"
        echo "  coka start [worker|main]       - Start/Restart kardan-e service"
        echo "  coka stop [worker|main|all]    - Stop kardan-e service"
        echo "  coka restart [worker|main|all] - Restart kardan-e service"
        echo "  coka logs [worker|main|live]   - Namayesh-e log-ha"
        echo "  coka update                    - Update kardan-e hamin script (coka)";;
esac
EOF

# --- Final Step: Make it executable ---
chmod +x "$COKA_SCRIPT_PATH"

print_success "Management script 'coka' (v4.0) installed successfully!"
echo
print_info "You can now manage your bot by typing 'coka' from anywhere on the server."
echo
coka
