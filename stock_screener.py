import pandas as pd
import streamlit as st
import yfinance as yf
import schedule
import time
from datetime import datetime

def fetch_stock_data(tickers):
    data = []
    for ticker in tickers:
        stock = yf.Ticker(ticker)
        info = stock.info
        try:
            data.append({
                'Ticker': ticker,
                'Price': info.get('currentPrice', 'N/A'),
                'Market Cap': info.get('marketCap', 'N/A'),
                'P/E Ratio': info.get('trailingPE', 'N/A'),
                'PEG Ratio': info.get('pegRatio', 'N/A'),
                'Debt/Equity': info.get('debtToEquity', 'N/A'),
                'ROE': info.get('returnOnEquity', 'N/A'),
                'Beta': info.get('beta', 'N/A'),
                'Volume': info.get('volume', 'N/A'),
                'Relative Volume': info.get('averageVolume', 'N/A'),
                'ATR': info.get('averageTrueRange', 'N/A')
            })
        except Exception as e:
            print(f"Error fetching data for {ticker}: {e}")
    return pd.DataFrame(data)

def analyze_stocks(df):
    df['Momentum Score'] = (df['Beta'] * df['Relative Volume']).fillna(0)
    df['Risk Score'] = (df['Debt/Equity'] * df['P/E Ratio']).fillna(0)
    df['Volatility Score'] = df['ATR'].fillna(0)
    df = df.sort_values(by=['Momentum Score', 'Volatility Score'], ascending=[False, False])
    return df

def run_daily_screening():
    tickers = ["AAPL", "MSFT", "TSLA", "AMZN", "NVDA", "GOOGL", "NFLX", "AMD", "META", "BA"]  # Expand with API integration
    df = fetch_stock_data(tickers)
    
    # Apply user-defined filters
    df = df[(df['Market Cap'] >= 1e9) & (df['Market Cap'] <= 500e9)]
    df = df[(df['P/E Ratio'] >= 1) & (df['P/E Ratio'] <= 20)]
    df = df[(df['PEG Ratio'] >= 0.1) & (df['PEG Ratio'] <= 1.5)]
    df = df[(df['Debt/Equity'] >= 0.1) & (df['Debt/Equity'] <= 2.5)]
    df = df[(df['ROE'] >= 0) & (df['ROE'] <= 0.2)]
    df = df[(df['Beta'] >= 1.5) & (df['Beta'] <= 4.0)]
    df = df[df['Volume'] >= 1000000]  # Increased volume for liquidity
    df = df[(df['Relative Volume'] >= 1.5) & (df['Relative Volume'] <= 5.0)]
    df = df[df['ATR'] >= 1.0]  # Ensures stock moves enough for day trading
    
    df = analyze_stocks(df)
    return df

def job():
    print("Running daily stock screener at:", datetime.now())
    screened_stocks = run_daily_screening()
    st.write("### 🔥 Top Stocks to Day Trade Today")
    st.dataframe(screened_stocks)
    top_stocks = screened_stocks.head(5)
    
    for _, stock in top_stocks.iterrows():
        st.write(f"## 🚀 {stock['Ticker']} - {stock['Price']} USD")
        st.write(f"**Momentum Score:** {stock['Momentum Score']:.2f} | **Volatility Score:** {stock['Volatility Score']:.2f} | **Risk Score:** {stock['Risk Score']:.2f}")
        st.write(f"Market Cap: {stock['Market Cap']} | P/E Ratio: {stock['P/E Ratio']} | Beta: {stock['Beta']}")
        st.write("---")

st.title("Finance Wizard-Style Stock Screener")
schedule.every().day.at("09:30").do(job)  # Runs daily at market open

while True:
    schedule.run_pending()
    time.sleep(60)
