import ccxt
import pandas as pd
import ta
from sklearn.tree import DecisionTreeClassifier
from sklearn.model_selection import train_test_split
from datetime import datetime
import time

# 1. Setup exchange
exchange = ccxt.binance()
symbol = 'BTC/USDT'

def fetch_data():
    ohlcv = exchange.fetch_ohlcv(symbol, timeframe='5m', limit=500)
    df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
    df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
    return df

def prepare_features(df):
    df['rsi'] = ta.momentum.RSIIndicator(df['close']).rsi()
    df['ema'] = ta.trend.EMAIndicator(df['close'], window=14).ema_indicator()
    df['macd'] = ta.trend.MACD(df['close']).macd_diff()
    df.dropna(inplace=True)
    df['target'] = (df['close'].shift(-1) > df['close']).astype(int)
    return df

def train_model(df):
    X = df[['rsi', 'ema', 'macd']]
    y = df['target']
    X_train, _, y_train, _ = train_test_split(X, y, shuffle=False)
    model = DecisionTreeClassifier()
    model.fit(X_train, y_train)
    return model

def predict_signal(df, model):
    df['signal'] = model.predict(df[['rsi', 'ema', 'macd']])
    df['final_signal'] = df['signal'].map({1: 'BUY', 0: 'SELL'})
    return df

def log_signal(df):
    if len(df) < 2:
        print("Not enough data to compute profit.")
        return

    signal_row = df.iloc[-2]
    next_row = df.iloc[-1]

    timestamp = signal_row['timestamp']
    signal = signal_row['final_signal']
    entry_price = signal_row['close']
    next_close = next_row['close']

    # ✅ Real profit percent (based on signal direction)
    if signal == 'BUY':
        profit_pct = ((next_close - entry_price) / entry_price) * 100
    else:  # 'SELL'
        profit_pct = ((entry_price - next_close) / entry_price) * 100

    profit_pct = round(profit_pct, 3)

    with open('signals.txt', 'a') as f:
        f.write(f"{timestamp} | {symbol} | Entry: {entry_price:.2f} | Signal: {signal} | Profit: {profit_pct}%\n")

    print(f"✅ {timestamp} | Signal: {signal} | Profit: {profit_pct}% | Logged.")
# 🔁 Loop forever
while True:
    try:
        df = fetch_data()
        df = prepare_features(df)
        model = train_model(df)
        df = predict_signal(df, model)
        log_signal(df)
    except Exception as e:
        print(f"❌ Error: {e}")
    time.sleep(300)  # 5 minutes
