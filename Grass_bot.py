import json
import time
import os
import sqlite3
import schedule
import requests
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from Crypto.Cipher import AES
from Crypto.Random import get_random_bytes
from base64 import b64encode, b64decode
import logging
import shutil
from datetime import datetime

# Setup logging
logging.basicConfig(filename='grass_bot.log', level=logging.INFO, 
                    format='%(asctime)s - %(levelname)s - %(message)s')

# Configuration
GOOGLE_SCOPES = ['https://www.googleapis.com/auth/userinfo.email']
GRASS_API_URL = "wss://api.getgrass.io/websocket"  # Placeholder: Replace with actual Grass WebSocket or API endpoint
BACKUP_DIR = "grass_backups"
DB_FILE = "grass_accounts.db"
ENCRYPTION_KEY_FILE = "encryption_key.bin"

# AES-256 Encryption/Decryption Helper Functions
def generate_encryption_key():
    key = get_random_bytes(32)  # AES-256 requires 32-byte key
    with open(ENCRYPTION_KEY_FILE, 'wb') as f:
        f.write(key)
    return key

def load_encryption_key():
    if not os.path.exists(ENCRYPTION_KEY_FILE):
        return generate_encryption_key()
    with open(ENCRYPTION_KEY_FILE, 'rb') as f:
        return f.read()

def encrypt_data(data, key):
    cipher = AES.new(key, AES.MODE_GCM)
    nonce = cipher.nonce
    ciphertext, tag = cipher.encrypt_and_digest(data.encode())
    return b64encode(nonce + ciphertext + tag).decode()

def decrypt_data(encrypted_data, key):
    try:
        data = b64decode(encrypted_data)
        nonce, ciphertext, tag = data[:16], data[16:-16], data[-16:]
        cipher = AES.new(key, AES.MODE_GCM, nonce=nonce)
        return cipher.decrypt_and_verify(ciphertext, tag).decode()
    except Exception as e:
        logging.error(f"Decryption failed: {e}")
        return None

# Database Setup
def init_database():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS accounts (
            email TEXT PRIMARY KEY,
            encrypted_token TEXT,
            login_status TEXT,
            last_points REAL,
            last_check TIMESTAMP
        )
    ''')
    conn.commit()
    conn.close()

# Google OAuth2 Login
def google_login(email):
    creds = None
    token_file = f"token_{email.replace('@', '_')}.json"
    encryption_key = load_encryption_key()

    if os.path.exists(token_file):
        try:
            with open(token_file, 'r') as f:
                encrypted_token = f.read()
            token_json = decrypt_data(encrypted_token, encryption_key)
            if token_json:
                creds = Credentials.from_authorized_user_info(json.loads(token_json))
                if creds.expired and creds.refresh_token:
                    creds.refresh(Request())
        except Exception as e:
            logging.error(f"Error loading token for {email}: {e}")

    if not creds or not creds.valid:
        flow = InstalledAppFlow.from_client_secrets_file('client_secrets.json', GOOGLE_SCOPES)
        creds = flow.run_local_server(port=0)
        encrypted_token = encrypt_data(json.dumps(creds.to_json()), encryption_key)
        with open(token_file, 'w') as f:
            f.write(encrypted_token)
        logging.info(f"New token generated for {email}")

    update_account_status(email, creds.to_json(), "SUCCESS")
    return creds

# Update account status in database
def update_account_status(email, token, status):
    encryption_key = load_encryption_key()
    encrypted_token = encrypt_data(token, encryption_key)
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('''
        INSERT OR REPLACE INTO accounts (email, encrypted_token, login_status, last_points, last_check)
        VALUES (?, ?, ?, ?, ?)
    ''', (email, encrypted_token, status, 0, datetime.now()))
    conn.commit()
    conn.close()

# Grass Farming Session (WebSocket-based, placeholder)
def start_farming_session(email, creds):
    try:
        import websocket
        ws = websocket.WebSocket()
        ws.connect(GRASS_API_URL, header={'Authorization': f'Bearer {creds.token}'})
        logging.info(f"Started farming session for {email}")
        
        # Simulate farming loop
        while True:
            ws.send(json.dumps({"action": "claim_rewards"}))  # Placeholder: Adjust based on Grass API
            response = json.loads(ws.recv())
            logging.info(f"Farming response for {email}: {response}")
            time.sleep(3600)  # Claim every hour (adjust as needed)
    except Exception as e:
        logging.error(f"Farming failed for {email}: {e}")
        update_account_status(email, creds.to_json(), "FAILED")
        return False
    return True

# Browser-based Farming (Alternative, if API is unavailable)
def start_browser_farming(email, creds):
    try:
        driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()))
        driver.get("https://app.getgrass.io")  # Replace with actual Grass login URL
        # Simulate Google login (requires specific selectors, customize as needed)
        driver.find_element_by_id("google_login_button").click()  # Placeholder
        time.sleep(2)
        driver.find_element_by_name("identifier").send_keys(email)
        driver.find_element_by_id("identifierNext").click()
        # Assume OAuth2 flow completes via creds (manual intervention may be needed)
        logging.info(f"Browser farming started for {email}")
        
        # Simulate reward claiming
        schedule.every(1).hours.do(lambda: driver.find_element_by_id("claim_rewards").click())  # Placeholder
        while True:
            schedule.run_pending()
            time.sleep(60)
    except Exception as e:
        logging.error(f"Browser farming failed for {email}: {e}")
        update_account_status(email, creds.to_json(), "FAILED")
        driver.quit()
        return False
    return True

# Retrieve and Display $GRASS Balance
def get_grass_balance(email, creds):
    try:
        response = requests.get("https://api.getgrass.io/balance",  # Placeholder: Replace with actual endpoint
                               headers={'Authorization': f'Bearer {creds.token}'})
        balance = response.json().get('balance', 0)
        logging.info(f"Balance for {email}: {balance} $GRASS")
        
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute('UPDATE accounts SET last_points = ?, last_check = ? WHERE email = ?',
                       (balance, datetime.now(), email))
        conn.commit()
        conn.close()
        return balance
    except Exception as e:
        logging.error(f"Failed to retrieve balance for {email}: {e}")
        return None

# Monitoring Function
def monitor_accounts():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('SELECT email, encrypted_token, last_points, last_check FROM accounts')
    accounts = cursor.fetchall()
    encryption_key = load_encryption_key()
    
    for email, encrypted_token, last_points, last_check in accounts:
        token = decrypt_data(encrypted_token, encryption_key)
        if not token:
            logging.error(f"Failed to decrypt token for {email}")
            continue
        creds = Credentials.from_authorized_user_info(json.loads(token))
        
        last_check_time = datetime.strptime(last_check, '%Y-%m-%d %H:%M:%S.%f')
        if (datetime.now() - last_check_time).total_seconds() > 3600:  # Check every 60 minutes
            balance = get_grass_balance(email, creds)
            if balance is not None and balance == last_points:
                logging.warning(f"No points earned for {email}. Restarting session.")
                update_account_status(email, token, "RESTARTING")
                start_farming_session(email, creds)  # Or start_browser_farming
            else:
                logging.info(f"Points still accumulating for {email}")

    conn.close()

# Backup Logs and Account Data
def backup_data():
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    backup_path = os.path.join(BACKUP_DIR, f"backup_{timestamp}")
    os.makedirs(backup_path, exist_ok=True)
    
    # Backup logs
    shutil.copy('grass_bot.log', os.path.join(backup_path, 'grass_bot.log'))
    
    # Backup database
    shutil.copy(DB_FILE, os.path.join(backup_path, DB_FILE))
    
    # Optionally, upload to cloud (e.g., Google Drive, requires additional setup)
    logging.info(f"Backup created at {backup_path}")

# Main Bot Logic
def main():
    init_database()
    os.makedirs(BACKUP_DIR, exist_ok=True)
    
    # Example email list (replace with your own)
    emails = ["user1@example.com", "user2@example.com"]
    
    # Start farming sessions for each account
    for email in emails:
        creds = google_login(email)
        if creds:
            # Choose either API-based or browser-based farming
            start_farming_session(email, creds)  # Or start_browser_farming(email, creds)
    
    # Schedule monitoring and backups
    schedule.every(60).minutes.do(monitor_accounts)
    schedule.every(1).hours.do(backup_data)
    
    while True:
        schedule.run_pending()
        time.sleep(60)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        logging.info("Bot stopped by user")
    except Exception as e:
        logging.error(f"Bot crashed: {e}")
