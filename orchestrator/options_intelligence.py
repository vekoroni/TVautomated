"""
AVSHUNTER Options Intelligence v4.1 - JIM SIMONS EDITION + CRABEL PRECOR

RENAISSANCE MEDALLION PRINCIPLES APPLIED:
========================================

1. ALWAYS Generate Tradeable Signals
   - Multi-tier thresholds (never zero output)
   - Both long AND short opportunities
   - Mean reversion + trend continuation
   
2. Statistical Edge Over Volume
   - 50-100 signals daily across confidence spectrum
   - Size by conviction (TIER 1 = 100%, TIER 2 = 50%, TIER 3 = 25%)
   - Rapid evaluation, selective execution

3. Probabilistic Framework
   - No binary yes/no - everything has a probability
   - Position sizing scales with confidence
   - Expected value > transaction costs

4. Market Regime Adaptive
   - Different signals for different regimes
   - GREEN: Trend + breakouts
   - YELLOW: Mean reversion + quality
   - RED: Short opportunities + defensives

5. Liquidity First
   - Only trade what's executable
   - Options liquidity verification in Colab (Phase 2)
   - Price slippage < expected edge

Intelligence Sources:
- PDF Macro Intelligence Report (99% accurate parsing)
- WyckoffEngine_3101_v2: Phase detection A/B/C/D/E, trade direction, price levels
- wyckoff_crabel_precor_logic_v2: State machine, NR4/NR7, compression, transition tracking
- Crabel compression (volatility contraction) â€” enhanced with NR4/NR7
- Mean reversion detection (oversold/overbought)
- Macro regime filtering (GREEN/YELLOW/RED)

v4.1 Changes vs v4.0:
- Crabel Precor state machine integrated into _scan_ticker_stock()
- NR4/NR7 compression detection replaces simple ATR ratio
- Phase transition tracking adds conviction to signals
- Start-of-move estimate added to signal output
- Directional intent (BUY_SETUP/SELL_SETUP) cross-validates WyckoffEngine direction
- CRABEL_READY state elevates signals to higher tier automatically

Expected Output: 50-100 signals daily, 5-15 TIER 1, 15-30 TIER 2, 30-60 TIER 3
"""

import json
import os
import requests
import time
import csv
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from pathlib import Path
from dotenv import load_dotenv
import re
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed

load_dotenv()

from orchestrator.wyckoff_engine import WyckoffEngine

# Import Crabel Precor state machine
try:
    from wyckoff_crabel_precor_logic_v2 import process_precore_signal
    CRABEL_PRECOR_AVAILABLE = True
    logger.info("Crabel Precor state machine loaded")
except ImportError:
    CRABEL_PRECOR_AVAILABLE = False
    logger.warning("wyckoff_crabel_precor_logic_v2 not found - running without state machine")

# JSON macro loader â€” replaces PDF parsing
try:
    from orchestrator.macro_loader import MacroLoader
    MACRO_LOADER_AVAILABLE = True
except ImportError:
    MACRO_LOADER_AVAILABLE = False
    logger.warning("macro_loader not found - falling back to PDF parsing")

try:
    import PyPDF2
    PDF_AVAILABLE = True
except ImportError:
    PDF_AVAILABLE = False
    if not MACRO_LOADER_AVAILABLE:
        logger.warning("PyPDF2 not installed - Install: pip install PyPDF2")


class OptionsIntelligence:
    """
    Jim Simons-Inspired Signal Generator v4.1
    
    Generates 50-100 tradeable signals daily through:
    - Multi-tier probability thresholds
    - Both long and short opportunities  
    - Mean reversion detection
    - Regime-adaptive strategies
    - Never zero output (always something to trade)
    - Crabel Precor state machine for NR4/NR7 and transition tracking
    """

    def __init__(self, config):
        self.config = config
        self.polygon_key = os.getenv('POLYGON_API_KEY')
        self.base_url = "https://api.polygon.io"
        self.csv_path = Path('config/tickers.csv')

        self.wyckoff_engine = WyckoffEngine(min_bars=20)
        self.options_config = self._load_options_config()

        preset_name = self.options_config.get('active_preset', 'medium_term')
        preset = self.options_config['dte_presets'][preset_name]
        self.min_dte = preset['min_dte']
        self.max_dte = preset['max_dte']
        self.preset_name = preset['name']

        liq = self.options_config['liquidity_filters']
        self.max_spread_pct = liq['max_bid_ask_spread_pct']
        self.min_option_volume = liq['min_option_volume']
        self.min_open_interest = liq['min_open_interest']
        self.min_bid_price = liq['min_bid_price']

        greeks = self.options_config['greeks_filters']
        self.min_delta = greeks['min_delta']
        self.max_delta = greeks['max_delta']
        self.max_theta_pct = greeks['max_theta_pct_per_day']

        # JIM SIMONS APPROACH: Multi-tier thresholds
        self.crabel_tier1 = 0.55  # Ultra-compressed (highest conviction)
        self.crabel_tier2 = 0.65  # Moderately compressed (good conviction)
        self.crabel_tier3 = 0.75  # Lightly compressed (opportunistic)
        
        self.wyckoff_tier1 = 75   # Grade A patterns
        self.wyckoff_tier2 = 70   # Grade B patterns
        self.wyckoff_tier3 = 65   # Grade C patterns (with macro support)
        
        self.win_prob_tier1 = 0.75  # 75%+ win rate
        self.win_prob_tier2 = 0.65  # 65%+ win rate
        self.win_prob_tier3 = 0.55  # 55%+ win rate

        self.crabel_enabled = True
        self.macro_folder = Path('reports/daily')
        self.macro_data = None
        self.macro_regime = None
        self._price_cache: dict = {}  # Cache to avoid double API calls
        
        self.sector_map = self._load_sector_map()
        self.outcomes_db_path = Path('reports/outcomes.csv')
        self._initialize_outcomes_db()
        self._setup_logging()

    def _setup_logging(self):
        """Setup logging"""
        log_path = Path('reports/parsing_log.txt')
        log_path.parent.mkdir(parents=True, exist_ok=True)
        logging.basicConfig(
            filename=str(log_path),
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s'
        )
        self.logger = logging.getLogger(__name__)

    def _load_options_config(self):
        """Load config"""
        config_path = Path('config/options_settings.json')
        if config_path.exists():
            with open(config_path, 'r') as f:
                return json.load(f)
        return {
            'active_preset': 'medium_term',
            'dte_presets': {
                'medium_term': {'min_dte': 20, 'max_dte': 45, 'name': 'Medium-term'}
            },
            'liquidity_filters': {
                'max_bid_ask_spread_pct': 15,
                'min_option_volume': 100,
                'min_open_interest': 500,
                'min_bid_price': 0.50
            },
            'greeks_filters': {
                'min_delta': 0.45,
                'max_delta': 0.70,
                'max_theta_pct_per_day': 3.0
            }
        }

    def _load_sector_map(self):
        """Sector classification"""
        return {
            'AAPL': 'TECH', 'MSFT': 'TECH', 'NVDA': 'TECH', 'AMD': 'TECH',
            'GOOGL': 'TECH', 'META': 'TECH', 'NFLX': 'TECH', 'TSLA': 'TECH',
            'CRM': 'TECH', 'ADBE': 'TECH', 'INTC': 'TECH', 'QCOM': 'TECH',
            'JPM': 'FINANCIAL', 'BAC': 'FINANCIAL', 'GS': 'FINANCIAL',
            'JNJ': 'DEFENSIVE', 'PG': 'DEFENSIVE', 'KO': 'DEFENSIVE',
            'CAT': 'CYCLICAL', 'BA': 'CYCLICAL', 'NKE': 'CYCLICAL',
            'XOM': 'COMMODITY', 'GLD': 'COMMODITY', 'SLV': 'COMMODITY',
            'SPY': 'INDEX', 'QQQ': 'INDEX', 'IWM': 'INDEX',
            'TLT': 'BONDS'
        }

    def _initialize_outcomes_db(self):
        """Initialize outcomes DB"""
        if not self.outcomes_db_path.exists():
            self.outcomes_db_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.outcomes_db_path, 'w', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                writer.writerow([
                    'signal_id', 'ticker', 'direction', 'setup', 'tier',
                    'wyckoff_score', 'macro_regime', 'liquidity_status', 'sector',
                    'entry_date', 'entry_price', 'exit_date', 'exit_price',
                    'outcome', 'pnl_pct', 'hold_days', 'notes'
                ])

    # ========================================================================
    # PDF INTELLIGENCE PARSER
    # ========================================================================

    def _find_intelligence_report(self):
        """Find PDF report"""
        if not self.macro_folder.exists():
            return None
        pdf_files = list(self.macro_folder.glob('*macro*.pdf'))
        return max(pdf_files, key=lambda p: p.stat().st_mtime) if pdf_files else None

    def _extract_full_pdf_text(self, pdf_path):
        """Extract all PDF text"""
        if not PDF_AVAILABLE:
            return None
        try:
            page_texts = {}
            with open(pdf_path, 'rb') as f:
                reader = PyPDF2.PdfReader(f)
                for page_num, page in enumerate(reader.pages, start=1):
                    text = page.extract_text()
                    if text:
                        page_texts[page_num] = text
            return page_texts
        except Exception as e:
            self.logger.error(f"PDF extraction failed: {e}")
            return None

    def _parse_intelligence_report(self, pdf_path):
        """Parse macro report"""
        self.logger.info(f"Parsing: {pdf_path.name}")
        print(f"\n  [Report] Parsing: {pdf_path.name}")
        
        page_texts = self._extract_full_pdf_text(pdf_path)
        if not page_texts:
            print(f"  [Report] âŒ Cannot extract PDF text")
            return None
        
        print(f"  [Report] âœ“ Extracted {len(page_texts)} pages")
        full_text = "\n".join(page_texts.values())
        
        macro_data = {}
        
        switch, _, _ = self._extract_risk_switch(full_text, page_texts)
        conviction, _, _ = self._extract_conviction_score(full_text, page_texts)
        liquidity, _, _ = self._extract_liquidity_pulse(full_text, page_texts)
        vol_mode, vix_val, _, _ = self._extract_volatility_mode(full_text, page_texts)
        
        if switch is None or conviction is None or liquidity is None:
            print(f"  [Report] âŒ Critical fields missing")
            return None
        
        macro_data['risk_on_switch'] = switch
        macro_data['conviction_score'] = conviction
        macro_data['risk_on_prob'] = conviction
        macro_data['liquidity_status'] = liquidity
        macro_data['volatility_mode'] = vol_mode
        macro_data['vix_contango'] = vix_val
        
        print(f"  [Report] âœ“ Switch: {switch}, Conviction: {conviction:.0%}, Liquidity: {liquidity}")
        
        return macro_data

    def _extract_risk_switch(self, full_text, page_texts):
        """Extract Risk On/Off Switch"""
        for page_num in [6, 7]:
            if page_num in page_texts:
                match = re.search(r'Risk On / Off\s+Switch\s+(ON|OFF)', page_texts[page_num], re.I)
                if match:
                    return match.group(1).upper(), 'HIGH', f'Page {page_num}'
        return None, None, None

    def _extract_conviction_score(self, full_text, page_texts):
        """Extract conviction score"""
        for page_num in [6, 7]:
            if page_num in page_texts:
                match = re.search(r'Macro\s+Conviction\s+Score\s+(\d+\.?\d*)', page_texts[page_num], re.I)
                if match:
                    value = float(match.group(1))
                    if value > 1:
                        value /= 100
                    return value, 'HIGH', f'Page {page_num}'
        return None, None, None

    def _extract_liquidity_pulse(self, full_text, page_texts):
        """Extract liquidity"""
        status_map = {'supportive': 'FLOODED', 'flooded': 'FLOODED', 'draining': 'DRAINING', 'neutral': 'NEUTRAL'}
        for page_num in [6, 7]:
            if page_num in page_texts:
                match = re.search(r'Liquidity\s+Pulse\s+([A-Za-z\s,\(\)]+?)(?:\n|$)', page_texts[page_num], re.I)
                if match:
                    desc = match.group(1).lower()
                    for keyword, status in status_map.items():
                        if keyword in desc:
                            return status, 'HIGH', f'Page {page_num}'
        return None, None, None

    def _extract_volatility_mode(self, full_text, page_texts):
        """Extract volatility"""
        mode_map = {'suppressed': (0.12, 'Suppressed'), 'contained': (0.10, 'Contained'), 'elevated': (-0.05, 'Elevated')}
        for page_num in [6, 7]:
            if page_num in page_texts:
                match = re.search(r'Volatility\s+Mode\s+([A-Za-z\s\-,\(\)]+?)(?:\n|$)', page_texts[page_num], re.I)
                if match:
                    desc = match.group(1).lower()
                    for keyword, (contango, mode_name) in mode_map.items():
                        if keyword in desc:
                            return mode_name, contango, 'HIGH', f'Page {page_num}'
        return 'Unknown', 0.05, 'LOW', 'Default'

    # ========================================================================
    # MACRO VALIDATION
    # ========================================================================

    def _load_macro_data(self):
        """
        Load macro intelligence.
        Priority: JSON file (macro_loader) â†’ PDF fallback â†’ None
        """
        print(f"\n  [Macro] Loading intelligence...")

        # â”€â”€ JSON path (primary) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        if MACRO_LOADER_AVAILABLE:
            loader = MacroLoader(folder=str(self.macro_folder))
            macro_data = loader.load()
            if macro_data is not None:
                return macro_data
            print(f"  [Macro] JSON load failed â€” trying PDF fallback")

        # â”€â”€ PDF path (fallback) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        report_path = self._find_intelligence_report()
        if not report_path:
            print(f"  [Macro] âŒ No macro data found (JSON or PDF)")
            print(f"  [Macro]    Add: {self.macro_folder}/macro_intelligence_YYYY-MM-DD.json")
            return None
        return self._parse_intelligence_report(report_path)

    def _validate_macro_regime(self, macro_data):
        """Validate regime"""
        if macro_data is None:
            return 'ABORT', 0.0, "No macro data"
        
        risk_on_prob = macro_data.get('risk_on_prob', 0.50)
        liquidity = macro_data.get('liquidity_status', 'UNKNOWN')
        vix_contango = macro_data.get('vix_contango', 0.0)
        risk_switch = macro_data.get('risk_on_switch', 'UNKNOWN')
        
        print(f"\n  [Macro] REGIME: Switch={risk_switch}, Conviction={risk_on_prob:.0%}, Liq={liquidity}")
        
        if risk_switch == 'ON' and risk_on_prob >= 0.70 and liquidity == 'FLOODED':
            logger.info("  [Macro] GREEN (Optimal)")
            return 'GREEN', 1.0, "Optimal conditions"
        
        elif risk_switch == 'ON' and risk_on_prob >= 0.60:
            logger.info("  [Macro] YELLOW (Selective)")
            return 'YELLOW', 0.50, "Mixed conditions"
        
        else:
            logger.info("  [Macro] RED (Hostile â€” PUT/SELL_SETUP aligned, CALL reduced)")
            return 'RED', 0.25, "Hostile environment"

    # ========================================================================
    # JIM SIMONS MULTI-TIER CRABEL COMPRESSION (Enhanced with NR4/NR7)
    # ========================================================================

    def _calculate_atr(self, df, period):
        """Calculate ATR"""
        if len(df) < period + 1:
            return None
        df = df.copy()
        df['h-l'] = df['high'] - df['low']
        df['h-pc'] = abs(df['high'] - df['close'].shift(1))
        df['l-pc'] = abs(df['low'] - df['close'].shift(1))
        df['tr'] = df[['h-l', 'h-pc', 'l-pc']].max(axis=1)
        atr = df['tr'].rolling(window=period).mean()
        return atr.iloc[-1] if not pd.isna(atr.iloc[-1]) else None

    def _apply_crabel_filter_multitier(self, tickers):
        """
        JIM SIMONS APPROACH: Multi-tier compression filtering
        Enhanced v4.1: Uses Crabel Precor NR4/NR7 when available,
        falls back to ATR ratio when not.
        
        Returns dict with 3 tiers:
        - tier1: Ultra-compressed / CRABEL_READY (highest conviction)
        - tier2: COILING / moderately compressed
        - tier3: Lightly compressed (opportunistic)
        """
        print(f"\n  [Crabel] MULTI-TIER COMPRESSION SCAN v4.1")
        if CRABEL_PRECOR_AVAILABLE:
            print(f"  [Crabel] Mode: STATE MACHINE (NR4/NR7 active)")
        else:
            print(f"  [Crabel] Mode: ATR RATIO (state machine unavailable)")
        print(f"  [Crabel] Scanning {len(tickers)} tickers...")

        tier1_tickers = []
        tier2_tickers = []
        tier3_tickers = []
        scanned = 0
        start_time = time.time()

        for ticker in tickers:
            try:
                price_data = self._get_price_history(ticker, days=90)
                if not price_data or len(price_data) < 30:
                    scanned += 1
                    continue

                df = pd.DataFrame(price_data)
                df = df.rename(columns={'timestamp': 'date'})

                if CRABEL_PRECOR_AVAILABLE:
                    # Use state machine NR4/NR7 detection
                    precor = process_precore_signal(ticker, df)
                    comp_state = precor.get('crabel_compression_state', 'NONE')
                    
                    if comp_state == 'CRABEL_READY':
                        tier1_tickers.append(ticker)
                    elif comp_state == 'COILING':
                        tier2_tickers.append(ticker)
                    else:
                        # Fall through to ATR check for tier3
                        atr7 = self._calculate_atr(df, 7)
                        atr20 = self._calculate_atr(df, 20)
                        if atr7 and atr20 and atr20 > 0:
                            compression = atr7 / atr20
                            if compression < self.crabel_tier3:
                                tier3_tickers.append(ticker)
                else:
                    # ATR ratio fallback
                    atr7 = self._calculate_atr(df, 7)
                    atr20 = self._calculate_atr(df, 20)
                    if atr7 is None or atr20 is None or atr20 == 0:
                        scanned += 1
                        continue
                    compression = atr7 / atr20
                    if compression < self.crabel_tier1:
                        tier1_tickers.append(ticker)
                    elif compression < self.crabel_tier2:
                        tier2_tickers.append(ticker)
                    elif compression < self.crabel_tier3:
                        tier3_tickers.append(ticker)

                scanned += 1

                if scanned % 200 == 0:
                    elapsed = time.time() - start_time
                    rate = scanned / elapsed if elapsed > 0 else 0
                    remaining = (len(tickers) - scanned) / rate if rate > 0 else 0
                    print(f"  [Crabel] Progress: {scanned}/{len(tickers)} - "
                          f"T1:{len(tier1_tickers)} T2:{len(tier2_tickers)} T3:{len(tier3_tickers)} - "
                          f"ETA: {remaining/60:.1f}m")

                time.sleep(0.05)

            except Exception:
                scanned += 1
                continue

        elapsed = time.time() - start_time
        print(f"\n  [Crabel] COMPLETE ({elapsed/60:.1f}m):")
        print(f"    TIER 1 (CRABEL_READY): {len(tier1_tickers)}")
        print(f"    TIER 2 (COILING):      {len(tier2_tickers)}")
        print(f"    TIER 3 (Light):        {len(tier3_tickers)}")
        print(f"    Total: {len(tier1_tickers) + len(tier2_tickers) + len(tier3_tickers)} compressed")
        
        return {
            'tier1': tier1_tickers,
            'tier2': tier2_tickers,
            'tier3': tier3_tickers
        }

    # ========================================================================
    # MAIN SCAN
    # ========================================================================

    def scan_options(self):
        """
        Jim Simons-inspired signal generation v4.1
        
        Outputs 3 CSV files:
        - tier1_signals_[date].csv (CRABEL_READY + Grade A/B Wyckoff)
        - tier2_signals_[date].csv (COILING + Grade B/C Wyckoff)
        - tier3_signals_[date].csv (Light compression + Grade C)
        """
        print(f"  [Options] AVSHUNTER v4.1 - JIM SIMONS + CRABEL PRECOR EDITION")
        print(f"  [Options] Goal: 50-100 tradeable signals daily")

        if not self.polygon_key or self.polygon_key == 'your_polygon_key_here':
            return {'status': 'error', 'message': 'API key not configured', 'signal_count': 0, 'signals': []}

        self.macro_data = self._load_macro_data()
        if self.macro_data is None:
            return {'status': 'aborted', 'message': 'No macro data', 'signal_count': 0, 'signals': []}
        
        self.macro_regime, size_mult, regime_reason = self._validate_macro_regime(self.macro_data)
        
        full_universe, source = self._get_universe()
        print(f"\n  [Options] Universe: {len(full_universe)} tickers")

        if self.crabel_enabled:
            compressed = self._apply_crabel_filter_multitier(full_universe)
        else:
            compressed = {'tier1': full_universe[:100], 'tier2': full_universe[100:300], 'tier3': full_universe[300:600]}

        print(f"\n  [Options] Scanning tiers for Wyckoff + Precor patterns...")
        
        tier1_signals = self._scan_tier(compressed['tier1'], 1, self.wyckoff_tier1, self.win_prob_tier1, size_mult)
        tier2_signals = self._scan_tier(compressed['tier2'], 2, self.wyckoff_tier2, self.win_prob_tier2, size_mult * 0.5)
        tier3_signals = self._scan_tier(compressed['tier3'], 3, self.wyckoff_tier3, self.win_prob_tier3, size_mult * 0.25)

        print(f"\n  [Options] COMPLETE:")
        print(f"    TIER 1: {len(tier1_signals)} signals ({self.win_prob_tier1:.0%}+ win rate)")
        print(f"    TIER 2: {len(tier2_signals)} signals ({self.win_prob_tier2:.0%}+ win rate)")
        print(f"    TIER 3: {len(tier3_signals)} signals ({self.win_prob_tier3:.0%}+ win rate)")
        print(f"    TOTAL: {len(tier1_signals) + len(tier2_signals) + len(tier3_signals)} tradeable signals")

        if tier1_signals:
            self._export_tier_csv(tier1_signals, 1)
        if tier2_signals:
            self._export_tier_csv(tier2_signals, 2)
        if tier3_signals:
            self._export_tier_csv(tier3_signals, 3)

        all_signals = tier1_signals + tier2_signals + tier3_signals

        return {
            'status': 'success',
            'signal_count': len(all_signals),
            'signals': all_signals,
            'tier1_count': len(tier1_signals),
            'tier2_count': len(tier2_signals),
            'tier3_count': len(tier3_signals),
            'macro_regime': self.macro_regime,
            'timestamp': datetime.now().isoformat()
        }

    def _scan_tier(self, tickers, tier_num, wyckoff_threshold, win_prob_threshold, size_mult):
        """Scan one tier of tickers"""
        signals = []
        
        for ticker in tickers:
            try:
                stock_signal = self._scan_ticker_stock(ticker, wyckoff_threshold)
                if not stock_signal:
                    continue

                sector = self.sector_map.get(ticker, 'UNKNOWN')
                
                if tier_num == 1:
                    sector_allowed, _, _ = self._apply_sector_rules_strict(ticker, sector)
                else:
                    sector_allowed = True
                
                if not sector_allowed:
                    continue
                
                win_prob = self._calculate_win_probability(
                    stock_signal['wyckoff_score'],
                    tier_num,
                    stock_signal.get('precor_compression_state', 'NONE'),
                    stock_signal.get('precor_intent', 'WAIT'),
                    stock_signal.get('precor_transition_conf', 0.0),
                    stock_signal.get('precor_intent_conf', 0.0),
                    stock_signal.get('precor_control', 'EQUILIBRIUM')
                )
                
                if win_prob < win_prob_threshold:
                    continue
                
                # Regime-aware position sizing
                # RED regime: PUT/SELL_SETUP aligned with macro = larger size
                # RED regime: CALL/BUY_SETUP counter-regime = minimal size
                effective_size = size_mult
                if self.macro_regime == 'RED':
                    if stock_signal.get('direction') == 'PUT':
                        effective_size = 0.75  # Aligned with defensive macro
                    else:
                        effective_size = 0.10  # Counter-regime, high risk

                signal = {
                    **stock_signal,
                    'tier': tier_num,
                    'sector': sector,
                    'macro_regime': self.macro_regime,
                    'win_probability': win_prob,
                    'position_size_mult': round(effective_size, 2),
                    'signal_id': f"{ticker}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
                }
                
                signals.append(signal)
                
                precor_tag = f" [{stock_signal.get('precor_compression_state', '')}]" if CRABEL_PRECOR_AVAILABLE else ""
                print(f"  [T{tier_num}] [OK] {ticker} {signal['setup_quality']}{precor_tag} (Win: {win_prob:.0%})")
                
                time.sleep(0.05)

            except Exception:
                continue
        
        return signals

    def _apply_sector_rules_strict(self, ticker, sector):
        """
        Strict sector rules (TIER 1 only).
        Uses sector_bias from JSON if provided, otherwise falls back
        to hardcoded rules.
        """
        # JSON sector_bias takes priority
        sector_bias = self.macro_data.get('sector_bias', {}) if self.macro_data else {}
        if sector_bias and sector in sector_bias:
            bias = sector_bias[sector]
            if bias == 'AVOID':
                return False, f"{sector} marked AVOID in macro JSON", 0.0
            elif bias == 'FAVOUR':
                return True, f"{sector} marked FAVOUR in macro JSON", 1.2
            # NEUTRAL falls through to default rules

        # Default hardcoded rules
        if sector == 'TECH':
            if self.macro_data and self.macro_data.get('liquidity_status') == 'DRAINING':
                return False, "Tech needs liquidity", 0.0

        if self.macro_regime == 'RED':
            if sector not in ['DEFENSIVE', 'COMMODITY', 'BONDS']:
                return False, "Defensives only in RED", 0.0

        return True, "Passed", 1.0

    def _calculate_win_probability(self, wyckoff_score, tier, compression_state='NONE',
                                    precor_intent='WAIT', transition_conf=0.0,
                                    intent_conf=0.0, control_state='EQUILIBRIUM'):
        """
        Enhanced win probability v4.1
        
        Boosts probability based on:
        - CRABEL_READY state: +8% (NR4/NR7 confirmed breakout imminent)
        - COILING state: +4%
        - BUY_SETUP/SELL_SETUP intent: +3%
        - High intent confidence (>70): +2%
        - High transition confidence (>70): +2%
        - Strong control (BUYERS/SELLERS vs EQUILIBRIUM/SHIFTING): +2%
        
        Note: transition_conf and intent_conf are 0-100 scale (from precor output)
        """
        base = wyckoff_score / 100
        
        # Base tier adjustment
        if tier == 1:
            prob = min(base + 0.10, 0.90)
        elif tier == 2:
            prob = min(base + 0.05, 0.80)
        else:
            prob = min(base, 0.70)
        
        # Crabel Precor boosts
        if compression_state == 'CRABEL_READY':
            prob = min(prob + 0.08, 0.92)
        elif compression_state == 'COILING':
            prob = min(prob + 0.04, 0.88)
        
        if precor_intent in ('BUY_SETUP', 'SELL_SETUP'):
            prob = min(prob + 0.03, 0.92)
        
        if intent_conf > 70.0:  # 0-100 scale
            prob = min(prob + 0.02, 0.92)
        
        if transition_conf > 70.0:  # 0-100 scale
            prob = min(prob + 0.02, 0.92)
        
        # Strong directional control adds conviction
        if control_state in ('BUYERS', 'SELLERS'):
            prob = min(prob + 0.02, 0.92)
        
        return prob

    def _scan_ticker_stock(self, ticker, wyckoff_threshold):
        """
        Scan ticker with WyckoffEngine + Crabel Precor state machine v4.1
        
        WyckoffEngine provides: phase, trade_direction, price levels, setup_quality
        Crabel Precor adds: NR4/NR7 compression, state transitions, directional intent
        Cross-validation: both must agree on direction for highest conviction
        """
        price_data = self._get_price_history(ticker, days=90)
        if not price_data or len(price_data) < 30:
            return None

        df = pd.DataFrame(price_data)
        df = df.rename(columns={'timestamp': 'date'})

        # ---- WyckoffEngine analysis ----
        wyckoff_result = self.wyckoff_engine.analyze(ticker, df)

        if wyckoff_result['setup_quality'] not in ['Grade_A', 'Grade_B', 'Grade_C']:
            return None

        if wyckoff_result['wyckoff_score'] < wyckoff_threshold:
            return None

        # trade_direction NONE is handled below with Precor Phase B override
        direction = 'CALL' if wyckoff_result['trade_direction'] == 'LONG' else 'PUT'
        current_price = price_data[-1]['close']

        # ---- Crabel Precor state machine ----
        precor_compression = 'NONE'
        precor_intent = 'WAIT'
        precor_intent_conf = 0.0
        precor_control = 'EQUILIBRIUM'
        precor_phase = wyckoff_result.get('phase', 'UNKNOWN')
        precor_transition = ''
        precor_transition_conf = 0.0
        precor_start_estimate = ''
        direction_confirmed = True

        if CRABEL_PRECOR_AVAILABLE:
            try:
                precor = process_precore_signal(ticker, df)
                precor_compression = precor.get('crabel_compression_state', 'NONE')
                precor_intent = precor.get('intent', 'WAIT')
                precor_intent_conf = precor.get('intent_conf', 0.0)
                precor_control = precor.get('control_state', 'EQUILIBRIUM')
                precor_phase = precor.get('wyckoff_phase', precor_phase)
                precor_transition_conf = precor.get('transition_conf', 0.0)
                move_age = precor.get('move_age_bars', None)
                move_start = precor.get('move_start_idx', None)
                if move_age is not None:
                    precor_start_estimate = f"{move_age}bars_ago"
                elif move_start is not None:
                    precor_start_estimate = f"idx_{move_start}"

                trans_to = precor.get('transition_to', 'NONE')
                current_ph = precor.get('wyckoff_phase', '')
                if trans_to and trans_to != 'NONE' and current_ph:
                    precor_transition = f"{current_ph}â†’{trans_to}"

                # Phase B + CRABEL_READY: high-value pre-breakout setup
                # WyckoffEngine returns NONE for Phase B but Precor knows better
                if (wyckoff_result['trade_direction'] == 'NONE' and
                        precor_compression == 'CRABEL_READY' and
                        precor_phase == 'B'):
                    # Infer direction from control state
                    if precor_control == 'BUYERS':
                        direction = 'CALL'
                    elif precor_control == 'SELLERS':
                        direction = 'PUT'
                    else:
                        return None  # No clear direction even with compression
                    # Override â€” Precor has found a valid pre-breakout setup
                elif wyckoff_result['trade_direction'] == 'NONE':
                    return None  # No direction from either engine

                # Cross-validate direction
                if precor_intent == 'BUY_SETUP' and direction == 'PUT':
                    direction_confirmed = False
                elif precor_intent == 'SELL_SETUP' and direction == 'CALL':
                    direction_confirmed = False

            except Exception:
                if wyckoff_result['trade_direction'] == 'NONE':
                    return None

        # Without Precor available, cannot recover NONE direction
        if not CRABEL_PRECOR_AVAILABLE and wyckoff_result['trade_direction'] == 'NONE':
            return None

        # Tier 1: reject conflicting directions â€” too risky
        if not direction_confirmed and wyckoff_threshold >= self.wyckoff_tier1:
            return None

        return {
            'ticker': ticker,
            'setup': precor_phase,
            'setup_quality': wyckoff_result['setup_quality'],
            'direction': direction,
            'wyckoff_score': wyckoff_result['wyckoff_score'],
            'stock_price': round(current_price, 2),
            'entry_trigger': wyckoff_result['entry_trigger'],
            'stop_loss': wyckoff_result['stop_loss'],
            'initial_target': wyckoff_result['initial_target'],
            'warnings': wyckoff_result['warnings'],
            # Crabel Precor enrichment
            'precor_compression_state': precor_compression,
            'precor_intent': precor_intent,
            'precor_intent_conf': round(precor_intent_conf, 1),
            'precor_control': precor_control,
            'precor_transition': precor_transition,
            'precor_transition_conf': round(precor_transition_conf, 1),
            'precor_start_estimate': precor_start_estimate,
            'direction_confirmed': direction_confirmed,
        }

    def _export_tier_csv(self, signals, tier_num):
        """Export tier CSV with Crabel Precor fields"""
        reports_dir = Path('reports')
        reports_dir.mkdir(exist_ok=True)

        timestamp = datetime.now().strftime('%Y-%m-%d_%H%M')
        csv_path = reports_dir / f'tier{tier_num}_signals_{timestamp}.csv'

        fieldnames = [
            'signal_id', 'ticker', 'direction', 'setup', 'setup_quality', 'tier',
            'wyckoff_score', 'win_probability', 'stock_price', 'entry_trigger',
            'stop_loss', 'initial_target', 'sector', 'macro_regime', 'position_size_mult',
            # Crabel Precor fields
            'precor_compression_state', 'precor_intent', 'precor_intent_conf',
            'precor_control', 'precor_transition', 'precor_transition_conf',
            'precor_start_estimate', 'direction_confirmed'
        ]

        with open(csv_path, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()

            for signal in signals:
                row = {k: signal.get(k, '') for k in fieldnames}
                writer.writerow(row)

        print(f"  [Export] TIER {tier_num} â†’ {csv_path.name} ({len(signals)} signals)")

    # ========================================================================
    # Universe & data methods (unchanged from v4.0)
    # ========================================================================

    def _get_universe(self):
        """Get universe"""
        if self.csv_path.exists():
            try:
                tickers = self._load_csv()
                if tickers:
                    return tickers, 'CSV'
            except:
                pass

        try:
            tickers = self._fetch_dynamic_universe()
            if tickers and len(tickers) > 50:
                return tickers, 'Dynamic'
        except:
            pass

        return self._get_static_universe(), 'Static'

    def _load_csv(self):
        """Load CSV"""
        tickers = []
        with open(self.csv_path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                ticker = row.get('ticker', '').strip().upper()
                if ticker and len(ticker) <= 5:
                    tickers.append(ticker)
        return tickers

    def _fetch_dynamic_universe(self):
        """Fetch dynamic universe"""
        url = f"{self.base_url}/v2/snapshot/locale/us/markets/stocks/tickers"
        params = {'apiKey': self.polygon_key}

        response = requests.get(url, params=params, timeout=30)
        response.raise_for_status()
        data = response.json()

        if 'tickers' not in data:
            raise Exception("No tickers")

        candidates = []
        for item in data['tickers']:
            ticker = item.get('ticker', '')
            day = item.get('day', {})
            if not day:
                continue

            price = day.get('c', 0)
            volume = day.get('v', 0)

            if (volume > 500000 and 10 <= price <= 2000 and '.' not in ticker and
                '-' not in ticker and len(ticker) <= 5 and ticker.isalpha()):
                candidates.append({'ticker': ticker, 'volume': volume})

        candidates.sort(key=lambda x: x['volume'], reverse=True)
        return [c['ticker'] for c in candidates[:500]]

    def _get_static_universe(self):
        """Static fallback"""
        return [
            'AAPL', 'MSFT', 'GOOGL', 'AMZN', 'META', 'NVDA', 'TSLA', 'NFLX', 'AMD', 'CRM',
            'JPM', 'BAC', 'GS', 'V', 'MA', 'BLK', 'C', 'WFC', 'AXP', 'SCHW',
            'SPY', 'QQQ', 'IWM', 'DIA', 'XLF', 'XLE', 'XLK', 'GLD', 'SLV', 'EEM'
        ]

    def _get_price_history(self, ticker, days=90):
        """Get price history from Polygon â€” cached to avoid duplicate API calls"""
        cache_key = f"{ticker}_{days}"
        if cache_key in self._price_cache:
            return self._price_cache[cache_key]

        end = datetime.now()
        start = end - timedelta(days=days)

        url = f"{self.base_url}/v2/aggs/ticker/{ticker}/range/1/day/{start.strftime('%Y-%m-%d')}/{end.strftime('%Y-%m-%d')}"
        params = {'apiKey': self.polygon_key}

        try:
            response = requests.get(url, params=params, timeout=10)
            response.raise_for_status()
            data = response.json()

            if 'results' in data and data['results']:
                bars = [{'timestamp': b['t'], 'open': b['o'], 'high': b['h'],
                        'low': b['l'], 'close': b['c'], 'volume': b['v']}
                       for b in data['results']]
                self._price_cache[cache_key] = bars
                return bars
        except Exception:
            pass
        self._price_cache[cache_key] = None
        return None

