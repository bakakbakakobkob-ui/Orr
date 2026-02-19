from flask import Flask, render_template, request, jsonify, send_from_directory
from datetime import datetime, timedelta
import qrcode
from io import BytesIO
import base64
import requests
import time
import os
from functools import wraps
from bakong_khqr import KHQR

app = Flask(__name__)

# --- ការកំណត់ (CONFIG) ---
ADMIN_PASSWORD = "1516Coolb"
API_TOKEN = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJkYXRhIjp7ImlkIjoiMmEyMDE3MzUxMGU4NDZhMiJ9LCJpYXQiOjE3NTk3MjIzNjAsImV4cCI6MTc2NzQ5ODM2MH0._d3PWPYi-N_mPyt-Ntxj5qbtHghOdtZhka2LbdJlKRw"
DATA_STORE_URL = 'https://orr-nu.vercel.app'
STORE_NAME = 'orr-nu'
TELEGRAM_BOT_TOKEN = "8441360171:AAF9SBXX7GJq9Th7cJLjT0YW-bRKq9SIRJs"

khqr = KHQR(API_TOKEN)
current_transactions = {}

# --- ADMIN DECORATOR ---
def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if request.args.get('pass') != ADMIN_PASSWORD:
            return "Unauthorized", 401
        return f(*args, **kwargs)
    return decorated_function

# --- LOAD PACKAGES (បញ្ចូលតម្លៃ ML 11 = 0.01 ត្រង់នេះ) ---
def load_packages():
    try:
        response = requests.get(f'{DATA_STORE_URL}/packages?store={STORE_NAME}', timeout=5)
        if response.status_code == 200:
            return response.json()
    except:
        pass
    
    # បើ API មិនដើរ វានឹងយកតម្លៃខាងក្រោមនេះ
    return {
        "ml": [
            {"name": "11 Diamonds", "price": 0.01, "package_id": "11"},
            {"name": "50 Diamonds", "price": 0.85, "package_id": "50"}
        ],
        "ff": [{"name": "100 Diamonds", "price": 0.90, "package_id": "100"}],
        "pubg": [{"name": "60 UC", "price": 0.95, "package_id": "60"}],
        "hok": [], "bloodstrike": [], "mcgg": [], "mlph": [],
        "ml_special_offers": [], "ff_special_offers": [], "pubg_special_offers": [],
        "hok_special_offers": [], "bloodstrike_special_offers": [], "mcgg_special_offers": [], "mlph_special_offers": []
    }

# --- ROUTES ---
@app.route('/')
@app.route('/mobile-legends')
@app.route('/free-fire')
@app.route('/pubg-mobile')
@app.route('/honor-of-kings')
def index():
    return render_template('index.html')

@app.route('/generate_qr', methods=['POST'])
def generate_qr():
    try:
        amount = float(request.form['amount'])
        player_id = request.form.get('player_id', '')
        zone_id = request.form.get('zone_id', '0')
        package = request.form.get('package', '')
        game_type = request.form.get('game_type', 'ml')

        # ឆែកមើលតម្លៃក្នុង Package
        packages = load_packages()
        all_pkgs = packages.get(game_type, []) + packages.get(f"{game_type}_special_offers", [])
        matched = next((p for p in all_pkgs if p.get('name') == package), None)
        
        if not matched or float(matched.get('price', 0)) != amount:
            return jsonify({'error': 'Price mismatch or package not found'}), 400

        # បង្កើត KHQR
        transaction_id = f"TRX{int(time.time())}"
        qr_data = khqr.create_qr(
            bank_account='meng_topup@aclb',
            merchant_name='Meng Topup',
            amount=amount,
            currency='USD',
            bill_number=transaction_id
        )
        
        # បង្កើតរូបភាព QR
        qr_img = qrcode.make(qr_data)
        img_io = BytesIO()
        qr_img.save(img_io, 'PNG')
        qr_base64 = base64.b64encode(img_io.getvalue()).decode('utf-8')
        
        expiry = datetime.now() + timedelta(minutes=3)
        current_transactions[transaction_id] = {
            'amount': amount,
            'md5_hash': khqr.generate_md5(qr_data),
            'expiry': expiry.isoformat(),
            'player_id': player_id,
            'zone_id': zone_id,
            'package': package,
            'game_type': game_type
        }
        
        return jsonify({
            'success': True, 
            'qr_image': qr_base64, 
            'transaction_id': transaction_id, 
            'expiry': expiry.isoformat()
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/check_payment', methods=['POST'])
def check_payment():
    transaction_id = request.form.get('transaction_id')
    if not transaction_id or transaction_id not in current_transactions:
        return jsonify({'error': 'Session not found'}), 400
        
    txn = current_transactions[transaction_id]
    
    # ឆែកមើលថាតើហួសពេល ៣ នាទីឬនៅ
    if datetime.now() > datetime.fromisoformat(txn['expiry']):
        return jsonify({'status': 'EXPIRED', 'final': True})

    # ឆែកការបង់ប្រាក់តាមរយៈ API
    try:
        res = requests.get(f"https://mengtopup.shop/api/check_payment?md5={txn['md5_hash']}", timeout=5)
        if res.status_code == 200 and res.json().get('status') == "PAID":
            # បើបង់រួច បញ្ជូនទៅ Telegram
            send_to_telegram(txn)
            del current_transactions[transaction_id]
            return jsonify({'status': 'PAID', 'final': True})
    except:
        pass
    
    return jsonify({'status': 'UNPAID', 'final': False})

def send_to_telegram(txn):
    # កំណត់ Command សម្រាប់ហ្គេមនីមួយៗ
    commands = {
        'ml': f"mlbb {txn['player_id']} {txn['zone_id']} {txn['package']}",
        'ff': f"ff {txn['player_id']} {txn['package']}",
        'pubg': f"pubg {txn['player_id']} 0000 {txn['package']}",
        'hok': f"hok {txn['player_id']} 0000 {txn['package']}"
    }
    
    cmd_text = commands.get(txn['game_type'], f"topup {txn['player_id']} {txn['package']}")
    invoice = f"💰 **បង់ប្រាក់ជោគជ័យ**\n💵 ចំនួន: ${txn['amount']}\n🎮 ហ្គេម: {txn['game_type']}\n🆔 ID: {txn['player_id']}"
    
    try:
        # ផ្ញើទៅ Group Process (កន្លែង Bot ដើរ)
        requests.post(f'https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage', 
                      json={'chat_id': '-1003284732983', 'text': cmd_text})
        # ផ្ញើទៅ Group វិក្កយបត្រ
        requests.post(f'https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage', 
                      json={'chat_id': '-1003157989347', 'text': invoice, 'parse_mode': 'Markdown'})
    except:
        pass

if __name__ == '__main__':
    app.run(debug=True)
