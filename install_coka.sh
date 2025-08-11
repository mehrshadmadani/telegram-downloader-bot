#!/bin/bash

# =============================================================
#         Coka Bot Manager - Universal Smart Installer
#              (Installer Script v2.0)
# =============================================================

COKA_SCRIPT_PATH="/usr/local/bin/coka"

# --- Functions ---
print_info() { echo -e "\e[34mINFO: $1\e[0m"; }
print_success() { echo -e "\e[32mSUCCESS: $1\e[0m"; }
print_error() { echo -e "\e[31mERROR: $1\e[0m"; }
print_warning() { echo -e "\e[33mWARNING: $1\e[0m"; }

# --- Main Logic ---

# Check if the coka command is already installed
if [ -f "$COKA_SCRIPT_PATH" ]; then
    # If it exists, just run the status command
    print_info "'coka' command is already installed. Showing current status..."
    echo
    /usr/local/bin/coka status
    exit 0
fi

# If not installed, proceed with the installation process
# Check for root privileges
if [ "$(id -u)" -ne 0 ]; then
  print_error "Installation requires root privileges. Please run with sudo."
  exit 1
fi

print_info "Welcome to the Coka Bot Manager installer!"
sleep 1

print_info "Step 1: Installing required utilities (screen, curl)..."
apt-get update -y > /dev/null 2>&1
apt-get install -y screen curl > /dev/null 2>&1
print_success "Utilities are ready."

print_info "Step 2: Creating the 'coka' management script..."

# --- Writing the coka script content using a Here Document ---
cat > "$COKA_SCRIPT_PATH" << 'EOF'
#!/bin/bash
# =============================================================
#         Coka Bot - Worker Management Script
# =============================================================

# --- Tanzimat (Settings) ---
VERSION="2.0"
# !!! MOHEM !!! Lotfan in 2 masir ra check konid.
BOT_DIR="/root/telegram-downloader-bot"
WORKER_GITHUB_URL="https://raw.githubusercontent.com/mehrshadmadani/telegram-downloader-bot/main/advanced_worker.py"
WORKER_SCREEN_NAME="worker_session"

# --- Functions ---
print_info() { echo -e "\e[34mINFO: $1\e[0m"; }
print_success() { echo -e "\e[32mSUCCESS: $1\e[0m"; }
print_error() { echo -e "\e[31mERROR: $1\e[0m"; }
print_warning() { echo -e "\e[33mWARNING: $1\e[0m"; }

is_worker_running() {
    screen -list | grep -q "$WORKER_SCREEN_NAME"
}

# --- Main Script Logic ---
cd "$BOT_DIR" || { print_error "Directory not found: $BOT_DIR"; exit 1; }

case "$1" in
    start)
        print_info "Ensuring worker is started..."
        if is_worker_running; then
            print_warning "Worker is already running. Restarting it to ensure a clean start..."
            screen -S "$WORKER_SCREEN_NAME" -X quit
            sleep 2
        fi
        screen -dmS "$WORKER_SCREEN_NAME" bash -c "source venv/bin/activate && python advanced_worker.py"
        sleep 2
        if is_worker_running; then
            print_success "Worker is now running in the background."
            print_info "Use 'coka logs live' to see the dashboard."
        else
            print_error "Failed to start worker. Check logs with 'coka logs file'."
        fi
        ;;
    stop)
        print_info "Attempting to stop the worker..."
        if ! is_worker_running; then
            print_error "Worker is not running."
            exit 1
        fi
        screen -S "$WORKER_SCREEN_NAME" -X quit
        print_success "Stop command sent to the worker."
        ;;
    restart)
        print_info "Restarting the worker..."
        coka stop
        sleep 2
        coka start
        ;;
    status)
        print_info "Coka Manager Version: $VERSION"
        print_info "Checking worker status..."
        if is_worker_running; then
            print_success "Worker is RUNNING."
            echo
            screen -list
        else
            print_warning "Worker is NOT RUNNING."
        fi
        ;;
    logs)
        case "$2" in
            file)
                print_info "Showing 'bot.log'. Press Ctrl+C to exit."
                tail -f bot.log
                ;;
            live)
                print_info "Attaching to the live worker dashboard..."
                print_warning "To detach, press Ctrl+A then D."
                sleep 2
                screen -r "$WORKER_SCREEN_NAME"
                ;;
            *)
                print_error "Estefadeh eshtebah. Bezan: coka logs [file|live]"
                ;;
        esac
        ;;
    update)
        print_info "Updating worker script from GitHub..."
        curl -s -o "${BOT_DIR}/advanced_worker.py" "$WORKER_GITHUB_URL"
        if [ $? -eq 0 ]; then
            print_success "Worker script updated successfully."
            print_warning "Baraye e'mal-e taghirat, worker ra restart kon: 'coka restart'"
        else
            print_error "Failed to download update from GitHub."
        fi
        ;;
    *)
        echo "Coka Worker Management Script - v$VERSION"
        echo "========================================"
        echo "Dastoorat-e Mojood (Available commands):"
        echo "  coka start         - Start/Restart kardan-e worker"
        echo "  coka stop          - Stop kardan-e worker"
        echo "  coka restart       - Restart kardan-e worker"
        echo "  coka status        - Namayesh-e vaziat"
        echo "  coka logs [file|live] - Namayesh-e log-ha"
        echo "  coka update        - Update kardan-e worker az GitHub"
        ;;
esac
EOF

# --- Final Step: Make it executable ---
chmod +x "$COKA_SCRIPT_PATH"

print_success "Management script 'coka' installed successfully!"
echo
print_warning ">>> MOHEM: Lotfan 2 Moghaddar zir ra dar file coka barresi konid:"
print_warning "nano $COKA_SCRIPT_PATH"
print_warning "1. BOT_DIR (Masir-e poosheh-ye robot)"
print_warning "2. WORKER_GITHUB_URL (Link-e file-e worker dar GitHub)"
