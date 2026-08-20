#!/usr/bin/env python3
"""
PREMARKET INTELLIGENCE ULTIMATE v1.0
Processes ULTIMATE discovery outputs for daily trading decisions

Reads:
- early_positions_ultimate_*.csv (Tier 0)
- discovery_candidates_ultimate_*.csv (All tiers)
- active_positions_*.csv (Tracking)

Outputs:
- Comprehensive action list across all tiers
- Prioritized entry recommendations
- Position monitoring updates
"""

import pandas as pd
from pathlib import Path
from datetime import datetime, timedelta
import logging
import sys
import io
# Fix Windows cp1252 terminal encoding — allows emoji/unicode in print()
if sys.stdout.encoding and sys.stdout.encoding.lower() != 'utf-8':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
if sys.stderr.encoding and sys.stderr.encoding.lower() != 'utf-8':
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')
from typing import Dict, List, Tuple, Optional
import argparse

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Paths
BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"
OUTPUT_DIR = DATA_DIR / "output"


class PremarketUltimate:
    """Process ULTIMATE discovery outputs for premarket actions"""
    
    def __init__(self):
        self.early_positions: pd.DataFrame = pd.DataFrame()
        self.all_candidates: pd.DataFrame = pd.DataFrame()
        self.active_positions: pd.DataFrame = pd.DataFrame()
        self.actions: List[Dict] = []
        
    def load_latest_file(self, pattern: str) -> Optional[pd.DataFrame]:
        """Load the most recent file matching pattern"""
        files = sorted(OUTPUT_DIR.glob(pattern))
        if not files:
            logger.warning(f"No files found matching: {pattern}")
            return None
        
        latest = files[-1]
        logger.info(f"  📂 {latest.name}")
        return pd.read_csv(latest)
    
    def load_signals(self):
        """Load all signal sources"""
        logger.info("\n📚 Loading ULTIMATE discovery outputs...")
        
        # Load early positions (Tier 0)
        self.early_positions = self.load_latest_file("early_positions_ultimate_*.csv")
        if self.early_positions is None:
            self.early_positions = pd.DataFrame()
        
        # Load all candidates (all tiers)
        self.all_candidates = self.load_latest_file("discovery_candidates_ultimate_*.csv")
        if self.all_candidates is None:
            self.all_candidates = pd.DataFrame()
        
        # Load active positions for tracking
        self.active_positions = self.load_latest_file("active_positions_*.csv")
        if self.active_positions is None:
            self.active_positions = pd.DataFrame()
    
    def generate_tier0_actions(self) -> List[Dict]:
        """Generate actions for Tier 0 (Early positions)"""
        actions = []
        
        if self.early_positions.empty:
            return actions
        
        # Filter for highest scores
        df = self.early_positions.copy()
        df = df.sort_values('early_formation_score', ascending=False)
        
        for _, row in df.iterrows():
            ticker = row['ticker']
            
            # Check if already in active positions
            already_active = False
            if not self.active_positions.empty:
                already_active = ticker in self.active_positions['ticker'].values
            
            action = {
                'ticker': ticker,
                'tier': 0,
                'tier_label': 'TIER_0_EARLY',
                'action': 'MONITOR_EARLY' if already_active else 'ENTER_EARLY',
                'entry_price': row.get('entry_price', 0),
                'stop_loss': row.get('stop_loss', 0),
                'entry_size': 0.33,
                'days_in_range': row.get('days_in_range', 0),
                'days_to_trigger': row.get('days_to_trigger', 0),
                'score': row.get('early_formation_score', 0),
                'compression_ratio': row.get('compression_ratio', 0),
                'phase': row.get('phase', 'UNKNOWN'),
                'conditions_met': row.get('conditions_met', ''),
                'crabel_state': row.get('crabel_state', 'NONE'),
                'control_state': row.get('control_state', 'UNKNOWN'),
            }
            
            actions.append(action)
        
        return actions
    
    def generate_tier1_actions(self) -> List[Dict]:
        """Generate actions for Tier 1 (Confirmed entries)"""
        actions = []
        
        if self.all_candidates.empty:
            return actions
        
        # Filter for Tier 1
        df = self.all_candidates[self.all_candidates['tier'] == 1].copy()
        df = df.sort_values('composite_score', ascending=False)
        
        for _, row in df.iterrows():
            ticker = row['ticker']
            
            # Check if graduated from early position
            graduated = False
            if not self.active_positions.empty:
                active = self.active_positions[self.active_positions['ticker'] == ticker]
                if not active.empty:
                    graduated = active.iloc[0].get('state', '') == 'EARLY_ENTERED'
            
            action = {
                'ticker': ticker,
                'tier': 1,
                'tier_label': 'TIER_1_CONFIRMED',
                'action': 'ADD_TO_EARLY' if graduated else 'ENTER_CONFIRMED',
                'entry_price': row.get('entry_price', 0),
                'stop_loss': row.get('stop_loss', 0),
                'entry_size': 0.67 if graduated else 1.0,
                'composite_score': row.get('composite_score', 0),
                'wyckoff_score': row.get('wyckoff_score', 0),
                'phase': row.get('phase', 'UNKNOWN'),
                'crabel_pattern': row.get('crabel_pattern', 'NONE'),
                'control_state': row.get('control_state', 'UNKNOWN'),
                'win_probability': row.get('win_probability', 0),
            }
            
            actions.append(action)
        
        return actions
    
    def generate_tier2_actions(self) -> List[Dict]:
        """Generate actions for Tier 2 (Observe)"""
        actions = []
        
        if self.all_candidates.empty:
            return actions
        
        # Filter for Tier 2
        df = self.all_candidates[self.all_candidates['tier'] == 2].copy()
        df = df.sort_values('wyckoff_score', ascending=False)
        
        for _, row in df.iterrows():
            action = {
                'ticker': row['ticker'],
                'tier': 2,
                'tier_label': 'TIER_2_OBSERVE',
                'action': 'OBSERVE',
                'entry_price': row.get('entry_price', 0),
                'stop_loss': row.get('stop_loss', 0),
                'wyckoff_score': row.get('wyckoff_score', 0),
                'phase': row.get('phase', 'UNKNOWN'),
                'control_state': row.get('control_state', 'UNKNOWN'),
            }
            
            actions.append(action)
        
        return actions
    
    def generate_actions(self):
        """Generate all actions across tiers"""
        logger.info("\n🎯 Generating action list...")
        
        tier0 = self.generate_tier0_actions()
        tier1 = self.generate_tier1_actions()
        tier2 = self.generate_tier2_actions()
        
        self.actions = tier0 + tier1 + tier2
        
        logger.info(f"  Tier 0 (Early): {len(tier0)} actions")
        logger.info(f"  Tier 1 (Confirmed): {len(tier1)} actions")
        logger.info(f"  Tier 2 (Observe): {len(tier2)} actions")
        logger.info(f"  TOTAL: {len(self.actions)} actions")
    
    def print_summary(self, top_n: int = 20):
        """Print comprehensive summary"""
        
        print("\n" + "=" * 80)
        print("📊 FULL SIGNAL REPORT")
        print("=" * 80)
        
        # Tier 0 summary
        tier0 = [a for a in self.actions if a['tier'] == 0]
        tier0_enter = [a for a in tier0 if a['action'] == 'ENTER_EARLY']
        tier0_monitor = [a for a in tier0 if a['action'] == 'MONITOR_EARLY']
        
        print(f"\n🎯 TIER 0 (EARLY POSITIONS): {len(tier0)} signals")
        print(f"   📥 ENTER (33% size): {len(tier0_enter)}")
        print(f"   📊 MONITOR (active): {len(tier0_monitor)}")
        
        # Tier 1 summary
        tier1 = [a for a in self.actions if a['tier'] == 1]
        tier1_enter = [a for a in tier1 if a['action'] == 'ENTER_CONFIRMED']
        tier1_add = [a for a in tier1 if a['action'] == 'ADD_TO_EARLY']
        
        print(f"\n🚨 TIER 1 (CONFIRMED ENTRIES): {len(tier1)} signals")
        print(f"   🎯 ENTER (100% size): {len(tier1_enter)}")
        print(f"   ➕ ADD TO EARLY (67% more): {len(tier1_add)}")
        
        # Tier 2 summary
        tier2 = [a for a in self.actions if a['tier'] == 2]
        print(f"\n📊 TIER 2 (OBSERVE): {len(tier2)} signals")
        
        # Total
        print(f"\n📈 TOTAL ACTIONABLE SIGNALS: {len(self.actions)}")
        
        # Top signals from each tier
        if tier0_enter:
            print("\n" + "=" * 80)
            print(f"🎯 TOP {min(top_n, len(tier0_enter))} EARLY POSITIONS (Tier 0)")
            print("=" * 80)
            
            for i, action in enumerate(tier0_enter[:top_n], 1):
                print(f"\n#{i}. {action['ticker']} 👀 | ENTER EARLY (33%)")
                print(f"     Entry: ${action['entry_price']:.2f} | Stop: ${action['stop_loss']:.2f}")
                print(f"     Days in Range: {action['days_in_range']} | To Trigger: {action['days_to_trigger']} days")
                print(f"     Score: {action['score']:.1f} | Compression: {action['compression_ratio']:.3f}")
                print(f"     Phase: {action['phase']} | Crabel: {action['crabel_state']} | Control: {action['control_state']}")
        
        if tier1_enter:
            print("\n" + "=" * 80)
            print(f"🚨 TOP {min(top_n, len(tier1_enter))} CONFIRMED ENTRIES (Tier 1)")
            print("=" * 80)
            
            for i, action in enumerate(tier1_enter[:top_n], 1):
                print(f"\n#{i}. {action['ticker']} 🎯 | ENTER CONFIRMED (100%)")
                print(f"     Entry: ${action['entry_price']:.2f} | Stop: ${action['stop_loss']:.2f}")
                print(f"     Composite Score: {action['composite_score']:.1f} | Win Prob: {action['win_probability']:.1f}%")
                print(f"     Phase: {action['phase']} | Crabel: {action['crabel_pattern']} | Control: {action['control_state']}")
        
        if tier1_add:
            print("\n" + "=" * 80)
            print(f"➕ GRADUATED POSITIONS (Add 67% to Early)")
            print("=" * 80)
            
            for i, action in enumerate(tier1_add[:10], 1):
                print(f"\n#{i}. {action['ticker']} ✅ | ADD TO EARLY (67% more)")
                print(f"     Entry: ${action['entry_price']:.2f} | Stop: ${action['stop_loss']:.2f}")
                print(f"     Composite Score: {action['composite_score']:.1f}")
        
        if tier2:
            print("\n" + "=" * 80)
            print(f"📊 TOP {min(10, len(tier2))} OBSERVE SIGNALS (Tier 2)")
            print("=" * 80)
            
            for i, action in enumerate(tier2[:10], 1):
                print(f"\n#{i}. {action['ticker']} 📊 | OBSERVE")
                print(f"     Wyckoff Score: {action['wyckoff_score']:.1f} | Phase: {action['phase']}")

        # ── EQUITY LANE — v1.1 ────────────────────────────────────────────────
        # Surfaces equity (stock) entries directly from Vanguard-passed signals.
        # These are the same tickers driving options analysis — now displayed as
        # direct stock trades for the portfolio equity lane.
        self._print_equity_lane(top_n)
    
    def _print_equity_lane(self, top_n: int = 20):
        """
        EQUITY LANE — v1.1
        Displays Tier 0 and Tier 1 signals as direct equity (stock) trades.
        These are the same signals feeding the options layer — surfaced here
        as a parallel portfolio lane: buy the stock, not just the option.

        Position sizing mirrors the options ladder intent:
          Tier 1 Confirmed  → Full equity position (up to max risk per trade)
          Tier 0 Early       → Starter equity position (33% of intended size)
        """
        tier0_equity = [a for a in self.actions if a['tier'] == 0 and a['action'] == 'ENTER_EARLY']
        tier1_equity = [a for a in self.actions if a['tier'] == 1 and a['action'] == 'ENTER_CONFIRMED']

        if not tier0_equity and not tier1_equity:
            return

        print("\n" + "=" * 80)
        print("📈 EQUITY LANE — DIRECT STOCK TRADES")
        print("   (Parallel to options — same signals, direct equity exposure)")
        print("=" * 80)

        if tier1_equity:
            print(f"\n🚨 TIER 1 EQUITY ENTRIES — FULL SIZE ({min(top_n, len(tier1_equity))} shown)")
            print("-" * 80)
            for i, action in enumerate(tier1_equity[:top_n], 1):
                entry  = action.get('entry_price', 0)
                stop   = action.get('stop_loss', 0)
                risk   = round(entry - stop, 2) if entry and stop else 0
                rr_target = round(entry + (risk * 2), 2) if risk > 0 else 0
                win_p  = action.get('win_probability', 0)
                phase  = action.get('phase', '?')
                crabel = action.get('crabel_pattern', 'NONE')
                ctrl   = action.get('control_state', '?')
                score  = action.get('composite_score', 0)
                print(f"\n  #{i}. {action['ticker']} | FULL POSITION (100%)")
                print(f"       Entry : ${entry:.2f}  |  Stop  : ${stop:.2f}  |  Risk/share: ${risk:.2f}")
                print(f"       2R Target: ${rr_target:.2f}  |  Win Prob: {win_p:.1f}%")
                print(f"       Phase: {phase}  |  Crabel: {crabel}  |  Control: {ctrl}")
                print(f"       Composite Score: {score:.1f}")

        if tier0_equity:
            print(f"\n👀 TIER 0 EQUITY STARTERS — 33% SIZE ({min(top_n, len(tier0_equity))} shown)")
            print("   (Enter now, add on Tier 1 confirmation)")
            print("-" * 80)
            for i, action in enumerate(tier0_equity[:top_n], 1):
                entry  = action.get('entry_price', 0)
                stop   = action.get('stop_loss', 0)
                risk   = round(entry - stop, 2) if entry and stop else 0
                days_t = action.get('days_to_trigger', 0)
                comp   = action.get('compression_ratio', 0)
                phase  = action.get('phase', '?')
                crabel = action.get('crabel_state', 'NONE')
                ctrl   = action.get('control_state', '?')
                score  = action.get('score', 0)
                print(f"\n  #{i}. {action['ticker']} | STARTER POSITION (33%)")
                print(f"       Entry : ${entry:.2f}  |  Stop : ${stop:.2f}  |  Risk/share: ${risk:.2f}")
                print(f"       Days to Trigger: {days_t}  |  Compression: {comp:.3f}")
                print(f"       Phase: {phase}  |  Crabel: {crabel}  |  Control: {ctrl}")
                print(f"       Early Score: {score:.1f}")

        print(f"\n  ── Equity Lane Summary ──")
        print(f"     Full positions (Tier 1): {len(tier1_equity)}")
        print(f"     Starters    (Tier 0)  : {len(tier0_equity)}")
        print(f"     Total equity trades   : {len(tier1_equity) + len(tier0_equity)}")
        print("=" * 80)

    def save_actions(self):
        """Save actions to CSV"""
        if not self.actions:
            logger.warning("No actions to save")
            return
        
        df = pd.DataFrame(self.actions)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filepath = OUTPUT_DIR / f"premarket_actions_ultimate_{timestamp}.csv"
        
        df.to_csv(filepath, index=False)
        logger.info(f"\n💾 Saved: {filepath.name}")
    
    def print_next_steps(self):
        """Print actionable next steps"""
        print("\n" + "=" * 80)
        print("📋 TRADING PRIORITIES")
        print("=" * 80)
        
        tier0_enter = len([a for a in self.actions if a['action'] == 'ENTER_EARLY'])
        tier1_enter = len([a for a in self.actions if a['action'] == 'ENTER_CONFIRMED'])
        tier1_add   = len([a for a in self.actions if a['action'] == 'ADD_TO_EARLY'])
        tier2_obs   = len([a for a in self.actions if a['action'] == 'OBSERVE'])

        print(f"\n1. 🎯 ENTER {tier1_enter} CONFIRMED SETUPS — OPTIONS (Tier 1)")
        print("   → 100% options position via options layer verdict")
        print("   → Pattern already triggered")
        print("   → Highest probability")

        print(f"\n2. 📈 ENTER {tier1_enter} CONFIRMED SETUPS — EQUITY LANE (Tier 1)")
        print("   → Full stock position alongside or instead of options")
        print("   → Same entry/stop as options signal")
        print("   → Compounds directly with price move — no theta drag")

        if tier1_add > 0:
            print(f"\n3. ➕ ADD TO {tier1_add} GRADUATED POSITIONS")
            print("   → Already have 33% from early entry")
            print("   → Add 67% more at confirmation (options + equity)")

        print(f"\n4. 👀 ENTER {tier0_enter} EARLY POSITIONS — OPTIONS + EQUITY (Tier 0)")
        print("   → 33% starter size in equity lane now")
        print("   → Options: LEAP or mid-dated where available")
        print("   → 5-10 days before trigger — better blended entry")

        print(f"\n5. 📊 MONITOR {tier2_obs} OBSERVE SIGNALS (Tier 2)")
        print("   → Watch for progression to Tier 1")
        print("   → Set alerts on both options and equity entries")

        print("\n" + "=" * 80)


def main():
    parser = argparse.ArgumentParser(description='Premarket Intelligence ULTIMATE')
    parser.add_argument('--top', type=int, default=20, help='Number of top signals to show (default: 20)')
    args = parser.parse_args()
    
    print("=" * 80)
    print("PREMARKET INTELLIGENCE ULTIMATE v1.1")
    print("=" * 80)
    print(f"Date: {datetime.now().strftime('%A, %B %d, %Y')}")
    print(f"Time: {datetime.now().strftime('%H:%M:%S')}")
    print("=" * 80)
    
    pm = PremarketUltimate()
    pm.load_signals()
    pm.generate_actions()
    pm.print_summary(top_n=args.top)
    pm.save_actions()
    pm.print_next_steps()
    
    print("\n" + "=" * 80)


if __name__ == "__main__":
    main()
