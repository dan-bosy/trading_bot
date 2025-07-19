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
    latest = df.iloc[-1]
    timestamp = latest['timestamp']
    signal = latest['final_signal']
    price = latest['close']
    with open('signals.txt', 'a') as f:
        f.write(f"{timestamp} | {symbol} | Price: {price:.2f} | Signal: {signal}\n")
    print(f"✅ {timestamp} | Signal: {signal} | Logged.")

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
