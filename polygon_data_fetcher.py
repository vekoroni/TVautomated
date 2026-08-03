"""
AVSHUNTER POLYGON DATA FETCHER v2.1
================================================================================
Production-grade Polygon.io integration with UNLIMITED rate limit support
- Daily bars (EOD data)
- Intraday bars (5min, 15min, 1hour)
- Real-time quotes
- Batch universe updates
- Automatic retries
- Data caching
================================================================================
API Key: set via POLYGON_API_KEY in .env — never hardcode here. This
         docstring carried a live key in plaintext until 2026-08-03;
         see REGIME_TREND_FIX_REPORT.md Stage D. The exposed key must
         be rotated at the Polygon dashboard, not just removed here.
Plan: Stock Screener Standard (UNLIMITED calls)
Rate Limit: UNLIMITED
================================================================================
"""

import os
import sys
import time
import json
import requests
import pandas as pd
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Callable
from pathlib import Path
import logging

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class RateLimiter:
    """
    Simple rate limiter that handles both limited and unlimited API plans
    """
    def __init__(self, calls_per_minute: int = 0):
        """
        Args:
            calls_per_minute: Max API calls per minute. 
                             0 = unlimited (Stock Screener Standard)
                             5 = limited (Starter plan)
        """
        self.calls_per_minute = calls_per_minute
        self.call_count = 0
        self.last_reset = time.time()
        self.is_unlimited = (calls_per_minute == 0)
    
    def wait_if_needed(self):
        """
        Block if rate limit would be exceeded.
        Does nothing if unlimited plan.
        """
        # Unlimited plan - no waiting needed
        if self.is_unlimited:
            return
        
        current_time = time.time()
        
        # Reset counter every 60 seconds
        if current_time - self.last_reset >= 60:
            self.call_count = 0
            self.last_reset = current_time
        
        # If limit reached, wait
        if self.call_count >= self.calls_per_minute:
            wait_time = 60 - (current_time - self.last_reset)
            if wait_time > 0:
                logger.info(f"Rate limit reached, waiting {wait_time:.1f}s...")
                time.sleep(wait_time + 1)
                self.call_count = 0
                self.last_reset = time.time()
        
        self.call_count += 1


class PolygonDataFetcher:
    """
    Polygon.io API client with automatic rate limiting and error handling
    """
    
    def __init__(self, api_key: Optional[str] = None):
        """
        Initialize Polygon data fetcher
        
        Args:
            api_key: Polygon API key (reads from .env if not provided)
        """
        # Get API key
        if api_key is None:
            from dotenv import load_dotenv
            load_dotenv()
            api_key = os.getenv('POLYGON_API_KEY')
            
        if not api_key:
            raise ValueError("POLYGON_API_KEY not found in environment or .env file")
        
        self.api_key = api_key
        self.base_url = "https://api.polygon.io"
        
        # Initialize with UNLIMITED rate limit (Stock Screener Standard plan)
        self.rate_limiter = RateLimiter(calls_per_minute=0)
        
        self.session = requests.Session()
        self.session.headers.update({'User-Agent': 'AVSHUNTER/2.1'})
        
        logger.info("✅ Polygon.io initialized")
        logger.info(f"   API Key: {api_key[:2]}...{api_key[-4:]}")
        logger.info(f"   Rate Limit: UNLIMITED")
    
    def fetch_daily_bars(
        self,
        ticker: str,
        from_date: str,
        to_date: str,
        adjusted: bool = True
    ) -> Optional[pd.DataFrame]:
        """
        Fetch daily OHLCV bars for a ticker
        
        Args:
            ticker: Stock symbol
            from_date: Start date (YYYY-MM-DD)
            to_date: End date (YYYY-MM-DD)
            adjusted: Use adjusted prices (splits/dividends)
        
        Returns:
            DataFrame with columns: date, open, high, low, close, volume
        """
        self.rate_limiter.wait_if_needed()
        
        endpoint = f"/v2/aggs/ticker/{ticker}/range/1/day/{from_date}/{to_date}"
        params = {
            'adjusted': 'true' if adjusted else 'false',
            'sort': 'asc',
            'limit': 50000,
            'apiKey': self.api_key
        }
        
        try:
            response = self.session.get(
                f"{self.base_url}{endpoint}",
                params=params,
                timeout=30
            )
            response.raise_for_status()
            data = response.json()
            
            # Accept both 'OK' and 'DELAYED' status (DELAYED = data exists but slightly delayed)
            if data.get('status') not in ['OK', 'DELAYED'] or not data.get('results'):
                logger.warning(f"No data for {ticker}")
                return None
            
            # Convert to DataFrame
            df = pd.DataFrame(data['results'])
            df['date'] = pd.to_datetime(df['t'], unit='ms')
            df = df.rename(columns={
                'o': 'open',
                'h': 'high',
                'l': 'low',
                'c': 'close',
                'v': 'volume'
            })
            df = df[['date', 'open', 'high', 'low', 'close', 'volume']]
            df = df.sort_values('date').reset_index(drop=True)
            
            return df
            
        except requests.exceptions.RequestException as e:
            logger.error(f"API error for {ticker}: {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error for {ticker}: {e}")
            return None
    
    def fetch_intraday_bars(
        self,
        ticker: str,
        multiplier: int,
        timespan: str,
        from_date: str,
        to_date: str
    ) -> Optional[pd.DataFrame]:
        """
        Fetch intraday bars (5min, 15min, 1hour, etc)
        
        Args:
            ticker: Stock symbol
            multiplier: Size of timespan (e.g., 5 for 5-minute bars)
            timespan: Unit (minute, hour)
            from_date: Start date (YYYY-MM-DD)
            to_date: End date (YYYY-MM-DD)
        
        Returns:
            DataFrame with OHLCV data
        """
        self.rate_limiter.wait_if_needed()
        
        endpoint = f"/v2/aggs/ticker/{ticker}/range/{multiplier}/{timespan}/{from_date}/{to_date}"
        params = {
            'adjusted': 'true',
            'sort': 'asc',
            'limit': 50000,
            'apiKey': self.api_key
        }
        
        try:
            response = self.session.get(
                f"{self.base_url}{endpoint}",
                params=params,
                timeout=30
            )
            response.raise_for_status()
            data = response.json()
            
            # Accept both 'OK' and 'DELAYED' status
            if data.get('status') not in ['OK', 'DELAYED'] or not data.get('results'):
                return None
            
            df = pd.DataFrame(data['results'])
            df['timestamp'] = pd.to_datetime(df['t'], unit='ms')
            df = df.rename(columns={
                'o': 'open',
                'h': 'high',
                'l': 'low',
                'c': 'close',
                'v': 'volume'
            })
            df = df[['timestamp', 'open', 'high', 'low', 'close', 'volume']]
            df = df.sort_values('timestamp').reset_index(drop=True)
            
            return df
            
        except Exception as e:
            logger.error(f"Error fetching intraday data for {ticker}: {e}")
            return None
    
    def fetch_current_price(self, ticker: str) -> Optional[float]:
        """
        Get current/last price for a ticker
        
        Args:
            ticker: Stock symbol
        
        Returns:
            Current price or None if unavailable
        """
        self.rate_limiter.wait_if_needed()
        
        endpoint = f"/v2/aggs/ticker/{ticker}/prev"
        params = {'adjusted': 'true', 'apiKey': self.api_key}
        
        try:
            response = self.session.get(
                f"{self.base_url}{endpoint}",
                params=params,
                timeout=15
            )
            response.raise_for_status()
            data = response.json()
            
            if data.get('status') == 'OK' and data.get('results'):
                return data['results'][0]['c']
            return None
            
        except Exception as e:
            logger.error(f"Error fetching price for {ticker}: {e}")
            return None
    
    def update_universe_data(
        self,
        tickers: List[str],
        output_dir: str = "data/daily",
        lookback_days: int = 60,
        progress_callback: Optional[Callable] = None
    ) -> Dict[str, str]:
        """
        Batch update OHLCV data for entire ticker universe
        
        Args:
            tickers: List of ticker symbols
            output_dir: Directory to save CSV files
            lookback_days: Number of historical days to fetch
            progress_callback: Optional callback(current, total, ticker)
        
        Returns:
            Dictionary with success/failure counts
        """
        # Create output directory
        Path(output_dir).mkdir(parents=True, exist_ok=True)
        
        # Date range
        end_date = datetime.now()
        start_date = end_date - timedelta(days=lookback_days)
        from_date = start_date.strftime('%Y-%m-%d')
        to_date = end_date.strftime('%Y-%m-%d')
        
        # Display header
        print("🔄 POLYGON UNIVERSE UPDATE")
        print("=" * 80)
        print(f"Tickers: {len(tickers)}")
        print(f"Period: {from_date} to {to_date}")
        print(f"Output: {output_dir}")
        
        # Calculate time estimate (only if limited plan)
        if self.rate_limiter.calls_per_minute > 0:
            est_minutes = len(tickers) / self.rate_limiter.calls_per_minute
            print(f"Est. time: {est_minutes:.1f} minutes")
        else:
            print(f"Est. time: ~{len(tickers) * 0.3 / 60:.1f} minutes (unlimited)")
        
        print(f"Rate limit: {'UNLIMITED' if self.rate_limiter.is_unlimited else f'{self.rate_limiter.calls_per_minute} calls/min'}")
        print("=" * 80)
        
        # Process tickers
        results = {'success': 0, 'failed': 0, 'errors': []}
        
        for i, ticker in enumerate(tickers, 1):
            try:
                # Fetch data
                df = self.fetch_daily_bars(ticker, from_date, to_date)
                
                if df is not None and len(df) > 0:
                    # Save to CSV
                    output_path = Path(output_dir) / f"{ticker}.csv"
                    df.to_csv(output_path, index=False)
                    results['success'] += 1
                    status = "✅"
                else:
                    results['failed'] += 1
                    results['errors'].append(f"{ticker}: No data")
                    status = "❌"
                
                # Progress callback (expects: current, total, ticker)
                if progress_callback:
                    progress_callback(i, len(tickers), ticker)
                
                # Progress display (every 100 tickers)
                if i % 100 == 0 or i == len(tickers):
                    pct = (i / len(tickers)) * 100
                    print(f"Progress: {i}/{len(tickers)} ({pct:.1f}%)", end='\r')
            
            except Exception as e:
                results['failed'] += 1
                results['errors'].append(f"{ticker}: {str(e)}")
                if progress_callback:
                    progress_callback(i, len(tickers), ticker)
        
        # Summary
        print("\n")
        print("=" * 80)
        print(f"✅ COMPLETE")
        print(f"   Success: {results['success']}/{len(tickers)} ({results['success']/len(tickers)*100:.1f}%)")
        print(f"   Failed: {results['failed']}/{len(tickers)}")
        
        if results['errors'] and len(results['errors']) <= 10:
            print("\nErrors:")
            for error in results['errors'][:10]:
                print(f"   • {error}")
        
        return results


def main():
    """Test the data fetcher"""
    fetcher = PolygonDataFetcher()
    
    # Test single ticker
    print("\n📊 Testing single ticker fetch...")
    df = fetcher.fetch_daily_bars('AAPL', '2026-01-01', '2026-02-04')
    if df is not None:
        print(f"✅ Fetched {len(df)} bars for AAPL")
        print(df.tail())
    else:
        print("❌ Failed to fetch AAPL data")
    
    # Test current price
    print("\n💰 Testing current price...")
    price = fetcher.fetch_current_price('AAPL')
    if price:
        print(f"✅ AAPL current price: ${price:.2f}")
    else:
        print("❌ Failed to fetch current price")


if __name__ == "__main__":
    main()
