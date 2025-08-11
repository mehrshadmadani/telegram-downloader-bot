#!/bin/bash

# =============================================================
#         Coka Bot Manager - Universal Interactive Installer v4.0
# =============================================================

COKA_SCRIPT_PATH="/usr/local/bin/coka"

# --- Functions ---
print_info() { echo -e "\e[34mINFO: $1\e[0m"; }
print_success() { echo -e "\e[32mSUCCESS: $1\e[0m"; }
print_error() { echo -e "\e[31mERROR: $1\e[0m"; }
print_warning() { echo -e "\e[33mWARNING: $1\e[0m"; }

# --- Main Logic ---

# Check for root privileges first
if [ "$(id -u)" -ne 0 ]; then
  print_error "This script must be run with sudo or as root."
  exit 1
fi

# If coka is already installed, ask for update confirmation
if [ -f "$COKA_SCRIPT_PATH" ]; then
    print_warning "'coka' command is already installed."
    read -p "Do you want to overwrite it with the version in this installer? (y/n): " OVERWRITE_CONFIRM
    if [[ "$OVERWRITE_CONFIRM" != "y" ]]; then
        print_info "Installation cancelled. Showing current status instead:"
        echo
        /usr/local/bin/coka status
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

# 2. Ask for the worker's raw GitHub URL
DEFAULT_WORKER_URL="https://raw.githubusercontent.com/mehrshadmadani/telegram-downloader-bot/main/advanced_worker.py"
read -p "Enter the raw GitHub URL for advanced_worker.py [Default: $DEFAULT_WORKER_URL]: " WORKER_URL_INPUT
WORKER_URL=${WORKER_URL_INPUT:-$DEFAULT_WORKER_URL}

echo
print_info "Using the following settings:"
echo "Bot Directory: $BOT_DIR"
echo "Worker Update URL: $WORKER_URL"
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

# --- Writing the coka script content using a Here Document ---
# We use placeholders and replace them with sed for safety
cat > /tmp/coka_template << 'EOF'
#!/bin/bash
VERSION="4.0 (Control Panel)"
BOT_DIR="__BOT_DIR_PLACEHOLDER__"
WORKER_GITHUB_URL="__WORKER_URL_PLACEHOLDER__"
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
        # ... (start logic from previous full response) ...
        ;;
    stop)
        # ... (stop logic from previous full response) ...
        ;;
    restart)
        coka stop "\$2"; sleep 2; coka start "\$2";
        ;;
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
        echo -e "\e[2m----------------------------------------------------------\e[0m"
        ;;
    logs)
        # ... (logs logic from previous full response) ...
        ;;
    update)
        print_info "Updating worker script from GitHub..."
        curl -s -o "\${BOT_DIR}/advanced_worker.py" "\$WORKER_GITHUB_URL"
        if [ \$? -eq 0 ]; then
            print_success "Worker script updated successfully."
            print_warning "Baraye e'mal-e taghirat, worker ra restart kon: 'coka restart worker'"
        else
            print_error "Failed to download update from GitHub."
        fi
        ;;
    *)
        coka status
        echo
        echo "Dastoorat-e Mojood (Available commands):"
        echo "  coka start [worker|main]       - Start/Restart kardan-e service"
        echo "  coka stop [worker|main|all]    - Stop kardan-e service"
        echo "  coka restart [worker|main|all] - Restart kardan-e service"
        echo "  coka logs [worker|main|live]   - Namayesh-e log-ha"
        echo "  coka update                    - Update kardan-e worker az GitHub"
        ;;
esac
EOF

# Replace placeholders with user-provided values
sed -i "s|__BOT_DIR_PLACEHOLDER__|$BOT_DIR|g" /tmp/coka_template
sed -i "s|__WORKER_URL_PLACEHOLDER__|$WORKER_URL|g" /tmp/coka_template

# Move the final script to the bin path
mv /tmp/coka_template "$COKA_SCRIPT_PATH"

# --- Final Step: Make it executable ---
chmod +x "$COKA_SCRIPT_PATH"

print_success "Management script 'coka' installed successfully!"
echo
print_info "You can now manage your bot by typing 'coka' from anywhere on the server."
echo
coka status
