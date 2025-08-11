#!/bin/bash

# =============================================================
#         Coka Downloader Bot - Universal Smart Installer
# =============================================================

# --- Settings ---
PROJECT_DIR="$HOME/telegram-downloader-bot"
COKA_SCRIPT_PATH="/usr/local/bin/coka"

# --- Functions for colorized output ---
print_info() { echo -e "\e[34mINFO: $1\e[0m"; }
print_success() { echo -e "\e[32mSUCCESS: $1\e[0m"; }
print_warning() { echo -e "\e[33mWARNING: $1\e[0m"; }
print_error() { echo -e "\e[31mERROR: $1\e[0m"; }

# Check for root privileges
if [ "$(id -u)" -ne 0 ]; then
  print_error "This script must be run with sudo or as root."
  exit 1
fi

print_info "Starting the complete installation of Coka Downloader Bot..."
sleep 2

# Step 1: Install System Dependencies
print_info "[1/7] Installing system dependencies (python, pip, venv, postgresql, ffmpeg, screen, git)..."
apt-get update -y > /dev/null 2>&1
apt-get install -y python3 python3-pip python3-venv postgresql postgresql-contrib ffmpeg screen git curl > /dev/null 2>&1
print_success "System dependencies installed."

# Step 2: Create Project Directory if it doesn't exist
print_info "[2/7] Checking for project directory at: $PROJECT_DIR"
if [ -d "$PROJECT_DIR" ]; then
    print_warning "Project directory already exists. Skipping file creation."
else
    mkdir -p "$PROJECT_DIR"
    cd "$PROJECT_DIR" || exit
    print_success "Project directory created."
    
    # Step 3: Create Project Files
    print_info "[3/7] Creating core bot files..."
    # ... (File creation logic remains here) ...
    print_success "Core bot files created successfully."
fi

cd "$PROJECT_DIR" || exit

# Step 4: Create 'coka' management script
print_info "[4/7] Installing/Updating the 'coka' management script..."
cat > "$COKA_SCRIPT_PATH" << 'EOF'
#!/bin/bash
# =============================================================
#         Coka Bot - Smart Worker Management Script
# =============================================================

# --- Tanzimat (Settings) ---
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
        print_info "Checking worker status..."
        if is_worker_running; then
            print_success "Worker is RUNNING."
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
        echo "Coka Worker Management Script"
        echo "============================="
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
chmod +x "$COKA_SCRIPT_PATH"
print_success "'coka' script installed/updated."

# Steps 5, 6, 7 are for a fresh install. We can wrap them in a check.
if [ ! -f "venv/bin/activate" ]; then
    # Setup PostgreSQL Database
    print_info "[5/7] Setting up PostgreSQL database for the first time..."
    # ... (Database setup logic) ...
    print_success "Database setup complete."

    # Setup Python Environment
    print_info "[6/7] Creating Python venv and installing dependencies..."
    # ... (Venv and pip install logic) ...
    print_success "Python environment is ready."
else
    print_info "[5-6/7] Skipping Database and Python setup (already exists)."
fi

# Final Instructions
print_info "[7/7] Setup process finished!"
echo
print_warning "=========================== NEXT STEPS ==========================="
print_warning "1. If this is a new install, edit the config file:"
print_warning "   nano $PROJECT_DIR/config.py"
echo
print_warning "2. Use the 'coka' command to manage your worker:"
print_warning "   coka start"
print_warning "   coka status"
print_warning "==================================================================="
