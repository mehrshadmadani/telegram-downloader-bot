#!/bin/bash

# =============================================================
#         Coka Bot Manager - Universal Smart Installer v34.0 (Full Control)
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

DEFAULT_BOT_DIR="/root/telegram-downloader-bot"
DEFAULT_MANAGER_URL="https://raw.githubusercontent.com/mehrshadmadani/telegram-downloader-bot/main/install_coka.sh"

if [ -f "$COKA_SCRIPT_PATH" ]; then
    print_warning "'coka' command is already installed."
    print_info "Fetching latest version info from GitHub..."
    LATEST_VERSION=$(curl -sL "$VERSION_URL?v=$(date +%s)" | head -n 1)
    if [ -z "$LATEST_VERSION" ]; then LATEST_VERSION="N/A"; fi
    
    EXISTING_BOT_DIR=$(grep -oP 'BOT_DIR="\K[^"]+' "$COKA_SCRIPT_PATH" || echo "$DEFAULT_BOT_DIR")
    EXISTING_MANAGER_URL=$(grep -oP 'MANAGER_SCRIPT_URL="\K[^"]+' "$COKA_SCRIPT_PATH" || echo "$DEFAULT_MANAGER_URL")
    DEFAULT_BOT_DIR=$EXISTING_BOT_DIR
    DEFAULT_MANAGER_URL=$EXISTING_MANAGER_URL
    
    read -p "Do you want to force overwrite it with the latest version from GitHub (v$LATEST_VERSION)? (y/n): " OVERWRITE_CONFIRM
    if [[ "$OVERWRITE_CONFIRM" != "y" ]]; then
        print_info "Installation cancelled."
        exit 0
    fi
else
    LATEST_VERSION=$(curl -sL "$VERSION_URL?v=$(date +%s)" | head -n 1)
    if [ -z "$LATEST_VERSION" ]; then LATEST_VERSION="34.0 (Full Control)"; fi
fi

# --- Interactive Setup ---
print_info "Configuring the 'coka' management command..."
read -p "Enter the full path to your bot directory [Default: $DEFAULT_BOT_DIR]: " BOT_DIR_INPUT
BOT_DIR=${BOT_DIR_INPUT:-$DEFAULT_BOT_DIR}
read -p "Enter the raw GitHub URL for this installer script itself [Default: $DEFAULT_MANAGER_URL]: " MANAGER_URL_INPUT
MANAGER_URL=${MANAGER_URL_INPUT:-$DEFAULT_MANAGER_URL}

# --- Installation ---
print_info "Installing required utilities (screen, curl, bc, postgresql-client)..."
apt-get update > /dev/null 2>&1
apt-get install -y screen curl bc postgresql-client > /dev/null 2>&1
print_info "Creating the 'coka' management script..."

# --- Writing the coka script content ---
cat > "$COKA_SCRIPT_PATH" << EOF
#!/bin/bash
VERSION="$LATEST_VERSION"
BOT_DIR="$BOT_DIR"
MANAGER_SCRIPT_URL="$MANAGER_URL"
CONFIG_URL="https://raw.githubusercontent.com/mehrshadmadani/telegram-downloader-bot/main/config.py.example"
REQS_SCRIPT_URL="https://raw.githubusercontent.com/mehrshadmadani/telegram-downloader-bot/main/requirements.txt"
WORKER_SCRIPT_URL="https://raw.githubusercontent.com/mehrshadmadani/telegram-downloader-bot/main/advanced_worker.py"
MAIN_BOT_SCRIPT_URL="https://raw.githubusercontent.com/mehrshadmadani/telegram-downloader-bot/main/main_bot.py"
VERSION_URL="https://raw.githubusercontent.com/mehrshadmadani/telegram-downloader-bot/main/version.txt"
WORKER_SCREEN_NAME="worker_session"
MAIN_BOT_SCREEN_NAME="main_bot_session"

# --- Functions ---
print_info() { echo -e "\e[34mINFO: \$1\e[0m"; }
print_success() { echo -e "\e[32mSUCCESS: \$1\e[0m"; }
print_error() { echo -e "\e[31mERROR: \$1\e[0m"; }
print_warning() { echo -e "\e[33mWARNING: \$1\e[0m"; }
is_running() { screen -list | grep -q "\$1"; }

get_config_value() {
    # Searches for a variable in a given config file
    # Usage: get_config_value "VAR_NAME" "/path/to/config.py"
    grep -oP "^\s*\$1\s*=\s*['\"]\K[^'\"]+" "\$2"
}

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
    local service_name=\$1; local script_url=\$2; local file_path=\$3
    print_warning "This will overwrite '\$file_path' with the latest version from GitHub."
    read -p "Are you sure? (y/n): " confirm
    if [[ "\$confirm" != "y" ]]; then print_info "Update for \$service_name cancelled."; return; fi
    print_info "Updating \$service_name script..."
    curl -s -L "\$script_url?v=\$(date +%s)" -o "\$file_path"
    if [ \$? -eq 0 ]; then
        print_success "\$service_name script updated successfully."
        if [[ "\$service_name" == "worker" ]] || [[ "\$service_name" == "main" ]]; then
            print_warning "Restart the service to apply changes: 'coka restart \$service_name'"
        fi
    else
        print_error "Failed to download update for \$service_name."
    fi
}

update_manager() {
    print_info "Checking for new version from GitHub..."
    LATEST_VERSION=\$(curl -sL "\$VERSION_URL?v=\$(date +%s)" | head -n 1)
    if [ -z "\$LATEST_VERSION" ]; then print_error "Could not fetch latest version info."; return; fi
    if [ "\$VERSION" == "\$LATEST_VERSION" ]; then print_success "You are already on the latest version (v\$VERSION)."; return; fi
    print_warning "A new version is available: v\$LATEST_VERSION"
    read -p "Do you want to update from v\$VERSION to v\$LATEST_VERSION? (y/n): " UPDATE_CONFIRM
    if [[ "\$UPDATE_CONFIRM" != "y" ]]; then print_info "Update cancelled."; return; fi
    print_info "Updating 'coka' manager script itself..."
    curl -s -L "\$MANAGER_SCRIPT_URL?v=\$(date +%s)" | sudo bash
    if [ \$? -eq 0 ]; then
        print_success "'coka' manager has been updated successfully!"
        print_info "Relaunching..."
        sleep 2
        exec coka
    else
        print_error "Failed to run update script.";
    fi
}

setup_requirements_cron() {
    CRON_FILE="/etc/cron.d/coka_requirements_update"
    CRON_COMMAND="cd \$BOT_DIR && source venv/bin/activate && pip install -r requirements.txt --upgrade"
    if [ -f "\$CRON_FILE" ]; then print_warning "Cron job already exists. It will be overwritten."; fi
    print_info "Setting up a weekly cron job to update Python libraries..."
    echo "0 3 * * 0 root \$CRON_COMMAND >> \$BOT_DIR/cron.log 2>&1" | sudo tee "\$CRON_FILE" > /dev/null
    print_success "Cron job created successfully."
}

remove_requirements_cron() {
    CRON_FILE="/etc/cron.d/coka_requirements_update"
    if [ -f "\$CRON_FILE" ]; then sudo rm -f "\$CRON_FILE"; print_success "Cron job removed."; else print_error "No active cron job found."; fi
}

clear_and_prepare_cookies() {
    print_warning "This will permanently delete all content in cookies.txt."
    read -p "Are you sure? (y/n): " confirm
    if [[ "\$confirm" != "y" ]]; then print_info "Operation cancelled."; return; fi
    print_info "Clearing cookies.txt..."; echo "# Netscape HTTP Cookie File" > "\$BOT_DIR/cookies.txt"; echo "# Paste new cookies here." >> "\$BOT_DIR/cookies.txt"
    print_success "cookies.txt is now clean and ready."
}

smart_update_config() {
    print_info "Starting smart update for config.py..."
    TEMP_CONFIG="/tmp/config.py.latest"; LOCAL_CONFIG="\$BOT_DIR/config.py"
    print_info "Downloading latest config template..."; curl -s -L "\$CONFIG_URL?v=\$(date +%s)" -o "\$TEMP_CONFIG"
    if [ \$? -ne 0 ] || [ ! -s "\$TEMP_CONFIG" ]; then print_error "Failed to download config template."; rm -f "\$TEMP_CONFIG"; return; fi
    local_vars=\$(grep -oP '^\s*\K[A-Z_]+(?=\s*=)' "\$LOCAL_CONFIG"); remote_vars=\$(grep -oP '^\s*\K[A-Z_]+(?=\s*=)' "\$TEMP_CONFIG")
    missing_vars=\$(comm -13 <(echo "\$local_vars" | sort) <(echo "\$remote_vars" | sort))
    if [ -z "\$missing_vars" ]; then print_success "Your config.py is already up to date."; rm -f "\$TEMP_CONFIG"; return; fi
    echo "" >> "\$LOCAL_CONFIG"; echo "# === Auto-added variables from Smart Update ===" >> "\$LOCAL_CONFIG"; ADDED_COUNT=0
    for var in \$missing_vars; do
        print_info "New variable found: '\$var'. Adding to config.py..."
        awk -v var="^\$var\s*=" '/\s*# ---.*---/,/^\s*\$/ { if (\$0 ~ var) p=1; if (p) print; if (p && \$0 ~ /^\s*\$/) p=0 }' "\$TEMP_CONFIG" >> "\$LOCAL_CONFIG"
        echo "" >> "\$LOCAL_CONFIG"; ADDED_COUNT=\$((ADDED_COUNT + 1))
    done
    print_success "\$ADDED_COUNT new variable(s) added."; print_warning "Please edit the file to set their values."
    rm -f "\$TEMP_CONFIG"
}

quick_update_config() {
    local TEMP_CONFIG="/tmp/config_temp.py"; local LOCAL_CONFIG="\$BOT_DIR/config.py"
    echo "# Paste your new config content here. Save and exit to apply." > "\$TEMP_CONFIG"; nano "\$TEMP_CONFIG"
    if [ \$(grep -cv '^#' "\$TEMP_CONFIG") -lt 2 ]; then print_error "File seems empty. Aborting."; rm -f "\$TEMP_CONFIG"; return; fi
    print_warning "This will REPLACE your current config.py."; read -p "Are you sure? (y/n): " confirm
    if [[ "\$confirm" == "y" ]]; then mv "\$TEMP_CONFIG" "\$LOCAL_CONFIG"; print_success "config.py updated."; print_warning "Restart bots to apply changes."; else rm -f "\$TEMP_CONFIG"; print_info "Quick update cancelled."; fi
}

install_database() {
    if command -v psql &> /dev/null; then 
        print_warning "PostgreSQL client appears to be installed."
    else
        print_info "Installing PostgreSQL..."; 
        apt-get update -y > /dev/null 2>&1
        apt-get install -y postgresql postgresql-contrib > /dev/null 2>&1
        print_success "PostgreSQL installed."
    fi
    
    print_info "Creating database user and database from config.py..."
    DB_NAME=\$(get_config_value "DB_NAME" "\$BOT_DIR/config.py"); DB_USER=\$(get_config_value "DB_USER" "\$BOT_DIR/config.py"); DB_PASS=\$(get_config_value "DB_PASS" "\$BOT_DIR/config.py")

    if sudo -u postgres psql -tAc "SELECT 1 FROM pg_database WHERE datname='\$DB_NAME'" | grep -q 1; then
        print_warning "Database '\$DB_NAME' already exists."
    else
        sudo -u postgres psql -c "CREATE DATABASE \$DB_NAME;"
        print_success "Database '\$DB_NAME' created."
    fi

    if sudo -u postgres psql -tAc "SELECT 1 FROM pg_roles WHERE rolname='\$DB_USER'" | grep -q 1; then
        print_warning "User '\$DB_USER' already exists."
    else
        sudo -u postgres psql -c "CREATE USER \$DB_USER WITH PASSWORD '\$DB_PASS';"
        print_success "User '\$DB_USER' created."
    fi
    
    sudo -u postgres psql -c "GRANT ALL PRIVILEGES ON DATABASE \$DB_NAME TO \$DB_USER;"
    print_success "Privileges granted."
    
    PG_VERSION=\$(psql -V | egrep -o '[0-9]{1,2}' | head -1)
    PG_HBA_PATH="/etc/postgresql/\$PG_VERSION/main/pg_hba.conf"
    if grep -q "local\s*\$DB_NAME\s*\$DB_USER" "\$PG_HBA_PATH"; then
        print_warning "pg_hba.conf already configured for this user/db."
    else
        echo "local   \$DB_NAME   \$DB_USER   scram-sha-256" | sudo tee -a "\$PG_HBA_PATH" > /dev/null
        print_info "Updated pg_hba.conf, restarting PostgreSQL..."
        sudo systemctl restart postgresql
    fi
    print_success "Database is ready."
}

show_db_users() {
    print_info "Showing last 20 users from database..."
    DB_NAME=\$(get_config_value "DB_NAME" "\$BOT_DIR/config.py"); DB_USER=\$(get_config_value "DB_USER" "\$BOT_DIR/config.py"); DB_PASS=\$(get_config_value "DB_PASS" "\$BOT_DIR/config.py"); DB_HOST=\$(get_config_value "DB_HOST" "\$BOT_DIR/config.py")
    export PGPASSWORD=\$DB_PASS; psql -U "\$DB_USER" -d "\$DB_NAME" -h "\$DB_HOST" -c "SELECT user_id, first_name, username FROM users ORDER BY join_date DESC LIMIT 20;"; export PGPASSWORD=""
}

# --- START: NEW SMART RESTORE FUNCTION ---
restore_bot_from_backup() {
    print_info "--- Smart Restore Bot & DB from Backup ---"
    read -p "Enter the full path of the backup file (.tar.gz): " backup_path
    if [ ! -f "\$backup_path" ]; then
        print_error "Backup file not found at: \$backup_path"
        return
    fi

    read -p "Enter the full path of the destination directory to extract to: " dest_path
    if [ -d "\$dest_path" ] && [ "\$(ls -A \$dest_path)" ]; then
        print_warning "Destination directory '\$dest_path' is not empty."
        read -p "Are you sure you want to extract into it? (y/n): " confirm_extract
        if [[ "\$confirm_extract" != "y" ]]; then
            print_info "Restore cancelled."
            return
        fi
    fi
    mkdir -p "\$dest_path"

    print_info "Extracting backup file..."
    tar -xzvf "\$backup_path" -C "\$dest_path" --strip-components=1
    if [ \$? -ne 0 ]; then
        print_error "Failed to extract the backup file."
        return
    fi
    print_success "Bot files extracted successfully to \$dest_path"

    local sql_file=\$(find "\$dest_path" -maxdepth 1 -name "*.sql" -type f | head -n 1)
    if [ -z "\$sql_file" ]; then
        print_warning "No .sql file found in the backup archive. Skipping database restore."
        return
    fi
    print_info "Database backup file found: \$sql_file"

    if ! command -v psql &> /dev/null; then
        print_error "PostgreSQL client is not installed. Database cannot be restored."
        print_info "Please run 'coka db' and select 'Install PostgreSQL' first."
        return
    fi

    print_error "!!! WARNING !!! The next step will DESTROY the current database and replace it with the backup."
    read -p "Are you sure you want to proceed with database restoration? (y/n): " confirm_db
    if [[ "\$confirm_db" != "y" ]]; then
        print_info "Database restore cancelled. Bot files remain extracted."
        return
    fi

    print_info "Reading database credentials from the newly extracted config.py..."
    local new_config_file="\$dest_path/config.py"
    if [ ! -f "\$new_config_file" ]; then
        print_error "config.py not found in the extracted directory. Cannot restore database."
        return
    fi
    
    DB_NAME=\$(get_config_value "DB_NAME" "\$new_config_file")
    DB_USER=\$(get_config_value "DB_USER" "\$new_config_file")
    DB_PASS=\$(get_config_value "DB_PASS" "\$new_config_file")
    DB_HOST=\$(get_config_value "DB_HOST" "\$new_config_file")
    
    print_info "Attempting to restore database '\$DB_NAME' for user '\$DB_USER'..."
    export PGPASSWORD=\$DB_PASS
    dropdb --if-exists -U "\$DB_USER" -h "\$DB_HOST" "\$DB_NAME"
    createdb -U "\$DB_USER" -h "\$DB_HOST" "\$DB_NAME"
    psql -U "\$DB_USER" -d "\$DB_NAME" -h "\$DB_HOST" -f "\$sql_file"
    export PGPASSWORD=""
    
    if [ \$? -eq 0 ]; then
        print_success "Database restored successfully."
        print_info "Restore complete! Remember to:"
        echo "  1. Set the new bot directory in the Coka manager if it's different ('coka update-manager')."
        echo "  2. Install Python requirements in the new directory ('cd \$dest_path && pip install -r requirements.txt')."
        echo "  3. Start the bots from the new directory."
    else
        print_error "An error occurred during database restoration."
    fi
}
# --- END: NEW SMART RESTORE FUNCTION ---

delete_database_data() {
    print_error "!!! WARNING !!! This will permanently delete ALL users and jobs from the database."
    read -p "This cannot be undone. Are you sure? (y/n): " confirm
    if [[ "\$confirm" != "y" ]]; then print_info "Operation cancelled."; return; fi
    print_info "Deleting and recreating tables..."
    DB_NAME=\$(get_config_value "DB_NAME" "\$BOT_DIR/config.py"); DB_USER=\$(get_config_value "DB_USER" "\$BOT_DIR/config.py"); DB_PASS=\$(get_config_value "DB_PASS" "\$BOT_DIR/config.py"); DB_HOST=\$(get_config_value "DB_HOST" "\$BOT_DIR/config.py")
    export PGPASSWORD=\$DB_PASS
    psql -U "\$DB_USER" -d "\$DB_NAME" -h "\$DB_HOST" -c "DROP TABLE IF EXISTS uploader_clicks, uploader_files, broadcast_messages, broadcast_history, uploader_links, general_settings, tutorial_texts, youtube_quality_settings, cached_files, jobs, users;"
    export PGPASSWORD=""
    print_success "All bot-related tables have been dropped."
    print_warning "Start the main bot once to allow it to recreate all tables automatically."
}

uninstall_postgresql() {
    print_error "!!! EXTREME WARNING !!!"; print_error "This will completely UNINSTALL PostgreSQL and DELETE ALL DATABASES on this server."
    read -p "This is a highly destructive action. Are you absolutely sure? (Type 'YES' to confirm): " confirm
    if [[ "\$confirm" != "YES" ]]; then print_info "Operation cancelled."; return; fi
    print_info "Stopping PostgreSQL service..."; systemctl stop postgresql
    print_info "Purging PostgreSQL packages..."; apt-get purge -y postgresql* postgresql-common; apt-get autoremove -y
    print_info "Removing configuration files..."; rm -rf /etc/postgresql/ /var/lib/postgresql/
    print_success "PostgreSQL has been completely removed from the server."
}

uninstall_coka() {
    print_warning "This will remove the 'coka' management script itself."
    read -p "Are you sure? (y/n): " confirm
    if [[ "\$confirm" != "y" ]]; then print_info "Operation cancelled."; return; fi
    if rm -f /usr/local/bin/coka; then print_success "'coka' script has been uninstalled."; else print_error "Failed to remove 'coka' script."; fi
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
    if ! command -v psql &> /dev/null; then DB_STATUS="\e[1;31mNOT INSTALLED\e[0m"; elif systemctl is-active --quiet postgresql; then DB_STATUS="\e[1;32mRUNNING\e[0m"; else DB_STATUS="\e[1;31mSTOPPED\e[0m"; fi

    echo -e "\e[1;35m
╔═════════════════════════════════════════════════════════════════════════════╗
║                          COKA BOT CONTROL PANEL                             ║
╚═════════════════════════════════════════════════════════════════════════════╝\e[0m"
    echo -e "  \e[1mCPU:\e[0m \e[1;37m\$CPU_USAGE \e[1m| RAM:\e[0m \e[1;37m\$MEM_INFO \e[1m| Disk:\e[0m \e[1;37m\$DISK_INFO"
    echo -e "\e[2m-------------------------------------------------------------------------------\e[0m"
    echo -e "  \e[1mServer IP:\e[0m \e[33m\$SERVER_IP\e[0m  \e[1mManager:\e[0m \e[36mv\$VERSION\e[0m"
    echo -e "  \e[1mWorker:\e[0m \$W_STATUS   \e[1mMain Bot:\e[0m \$M_STATUS   \e[1mDatabase:\e[0m \$DB_STATUS"
    echo -e "\e[2m-------------------------------------------------------------------------------\e[0m"
}

worker_menu() {
    while true; do
        show_panel_and_menu; echo "  Worker Manager Menu:"; echo "  [1] Start/Restart [2] Stop [3] Live Dashboard [4] Log File [5] Update [0] Back"
        read -p "  Enter your choice: " choice
        case \$choice in 1) start_service "worker" "\$WORKER_SCREEN_NAME" "advanced_worker.py";; 2) stop_service "worker" "\$WORKER_SCREEN_NAME" ;; 3) screen -r "\$WORKER_SCREEN_NAME" ;; 4) tail -f worker.log ;; 5) update_script "worker" "\$WORKER_SCRIPT_URL" "\$BOT_DIR/advanced_worker.py" ;; 0) return ;; *) print_error "Invalid." ;; esac
        echo; read -p "Press [Enter] to continue..."
    done
}

main_bot_menu() {
     while true; do
        show_panel_and_menu; echo "  Main Bot Manager Menu:"; echo "  [1] Start/Restart [2] Stop [3] Log File [4] Update [0] Back"
        read -p "  Enter your choice: " choice
        case \$choice in 1) start_service "main" "\$MAIN_BOT_SCREEN_NAME" "main_bot.py" ;; 2) stop_service "main" "\$MAIN_BOT_SCREEN_NAME" ;; 3) tail -f main_bot.log ;; 4) update_script "main" "\$MAIN_BOT_SCRIPT_URL" "\$BOT_DIR/main_bot.py" ;; 0) return ;; *) print_error "Invalid." ;; esac
        echo; read -p "Press [Enter] to continue..."
    done
}

requirements_menu() {
    while true; do
        show_panel_and_menu; echo "  Requirements Manager:"; echo "  [1] View [2] Update from GitHub [3] Setup Cron [4] Remove Cron [0] Back"
        read -p "  Enter your choice: " choice
        case \$choice in 1) cat -n "\$BOT_DIR/requirements.txt";; 2) update_script "requirements" "\$REQS_SCRIPT_URL" "\$BOT_DIR/requirements.txt" ;; 3) setup_requirements_cron ;; 4) remove_requirements_cron ;; 0) return ;; *) print_error "Invalid." ;; esac
        echo; read -p "Press [Enter] to continue..."
    done
}

cookies_menu() {
    while true; do
        show_panel_and_menu; echo "  Cookie Manager:"; echo "  [1] View [2] Clear & Prepare [3] Manual Edit (Nano) [0] Back"
        read -p "  Enter your choice: " choice
        case \$choice in 1) cat -n "\$BOT_DIR/cookies.txt";; 2) clear_and_prepare_cookies ;; 3) nano "\$BOT_DIR/cookies.txt" ;; 0) return ;; *) print_error "Invalid." ;; esac
        echo; read -p "Press [Enter] to continue..."
    done
}

config_menu() {
    while true; do
        show_panel_and_menu; echo "  Config Manager:"; echo "  [1] View [2] Manual Edit (Nano) [3] Smart Update [4] Quick Manual Update [0] Back"
        read -p "  Enter your choice: " choice
        case \$choice in 1) cat -n "\$BOT_DIR/config.py";; 2) nano "\$BOT_DIR/config.py" ;; 3) smart_update_config ;; 4) quick_update_config ;; 0) return ;; *) print_error "Invalid." ;; esac
        echo; read -p "Press [Enter] to continue..."
    done
}

database_menu() {
    while true; do
        show_panel_and_menu; echo "  Database Manager:"; echo "  [1] Install PostgreSQL & Setup"; echo "  [2] Show Bot Users List"; echo "  [3] Smart Restore from Backup (.tar.gz)"; echo "  [4] Delete ALL Bot Data"; echo "  [5] UNINSTALL PostgreSQL"; echo "  [0] Back"
        read -p "  Enter your choice: " choice
        case \$choice in 1) install_database ;; 2) show_db_users ;; 3) restore_bot_from_backup ;; 4) delete_database_data ;; 5) uninstall_postgresql ;; 0) return ;; *) print_error "Invalid." ;; esac
        echo; read -p "Press [Enter] to continue..."
    done
}

main_menu() {
    while true; do
        show_panel_and_menu
        echo "  Main Menu:"
        echo "  [1] Worker Manager"
        echo "  [2] Main Bot Manager"
        echo "  [3] Database Manager"
        echo "  [4] Requirements Manager"
        echo "  [5] Cookie Manager"
        echo "  [6] Config Manager"
        echo "  [7] Update This Manager (coka)"
        echo "  [8] Uninstall coka"
        echo "  [0] Quit"
        echo -e "\e[2m-------------------------------------------------------------------------------\e[0m"
        read -p "  Enter your choice: " choice
        case \$choice in 1) worker_menu ;; 2) main_bot_menu ;; 3) database_menu ;; 4) requirements_menu ;; 5) cookies_menu ;; 6) config_menu ;; 7) update_manager; ;; 8) uninstall_coka ;; 0) echo "Exiting."; clear; exit 0 ;; *) print_error "Invalid option." ;; esac
    done
}

# --- Main Script ---
# Change to the bot directory defined during install. If it fails, exit.
cd "\$BOT_DIR" 2>/dev/null || { 
    # Fallback for first run or if directory moved.
    if [ -d "/root/telegram-downloader-bot" ]; then
        cd "/root/telegram-downloader-bot"
    else
       print_error "Bot directory '\$BOT_DIR' not found. Please edit the script at /usr/local/bin/coka or reinstall."
       exit 1
    fi
}
main_menu
EOF

# --- Final Step ---
chmod +x "$COKA_SCRIPT_PATH"
print_success "Management script 'coka' (v$LATEST_VERSION) installed successfully!"
echo
coka
