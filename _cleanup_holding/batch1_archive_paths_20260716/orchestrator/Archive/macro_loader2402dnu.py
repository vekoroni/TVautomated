"""
AVSHUNTER Macro Intelligence Loader v1.0
========================================

Replaces PDF parsing with JSON file loading.
Place macro_intelligence_YYYY-MM-DD.json in reports/daily/
System automatically picks the most recent file.

Usage:
    from orchestrator.macro_loader import MacroLoader
    loader = MacroLoader()
    macro_data = loader.load()
    if macro_data is None:
        # handle missing file
"""

import json
import os
from pathlib import Path
from datetime import datetime, timezone
import logging

logger = logging.getLogger(__name__)


# ── Valid values for each field ───────────────────────────────────────────────

VALID_VALUES = {
    'risk_on_switch':      {'ON', 'OFF'},
    'regime_state':        {'Risk-On', 'Risk-Off', 'Transitional', 'Crisis', 'Recovery'},
    'dir_bias':            {'Bullish', 'Neutral-Bullish', 'Neutral', 'Neutral-Defensive',
                            'Bearish', 'Strongly-Bearish'},
    'regime_drift_status': {'Stable', 'Drifting', 'Accelerating', 'Reversing'},
    'macro_conviction':    {'Low', 'Medium', 'High'},
    'liquidity_status':    {'FLOODED', 'STABLE', 'NEUTRAL', 'DRAINING'},
    'volatility_mode':     {'Suppressed', 'Contained', 'Elevated', 'Expanding',
                            'Expanding-Front-Loaded', 'Unknown'},
    'sector_bias_values':  {'FAVOUR', 'NEUTRAL', 'AVOID'},
}

REQUIRED_FIELDS = [
    'risk_on_switch',
    'regime_state',
    'dir_bias',
    'regime_drift_status',
    'conviction_score',
    'macro_conviction',
    'liquidity_status',
    'volatility_mode',
    'vix_contango',
    'report_date',
    'as_of_utc',
]

OPTIONAL_FIELDS = ['sector_bias', 'notes']


class MacroLoader:
    """
    Loads macro intelligence from JSON file.
    Validates all fields, provides defaults for optional fields,
    raises clear errors for missing/invalid required fields.
    """

    def __init__(self, folder: str = 'reports/daily'):
        self.folder = Path(folder)

    def load(self) -> dict | None:
        """
        Find and load the most recent macro JSON file.
        Returns validated dict or None if no file found.
        """
        json_path = self._find_latest_json()

        if json_path is None:
            print(f"  [Macro] ❌ No macro_intelligence_*.json found in {self.folder}")
            print(f"  [Macro]    Copy template to: {self.folder}/macro_intelligence_YYYY-MM-DD.json")
            return None

        print(f"  [Macro] Loading: {json_path.name}")

        try:
            with open(json_path, 'r', encoding='utf-8') as f:
                raw = json.load(f)
        except json.JSONDecodeError as e:
            print(f"  [Macro] ❌ JSON parse error in {json_path.name}: {e}")
            return None
        except Exception as e:
            print(f"  [Macro] ❌ Cannot read {json_path.name}: {e}")
            return None

        # Strip instruction/guide keys (start with _)
        data = {k: v for k, v in raw.items() if not k.startswith('_')}

        errors = self._validate(data)
        if errors:
            print(f"  [Macro] ❌ Validation errors in {json_path.name}:")
            for err in errors:
                print(f"  [Macro]    • {err}")
            return None

        macro_data = self._normalise(data)
        age_hours = self._age_hours(macro_data.get('as_of_utc', ''))
        age_str = f"{age_hours:.1f}h ago" if age_hours is not None else "age unknown"

        print(f"  [Macro] ✓ Loaded {json_path.name} ({age_str})")
        print(f"  [Macro] ✓ Switch: {macro_data['risk_on_switch']}, "
              f"Conviction: {macro_data['conviction_score']:.0%}, "
              f"Liquidity: {macro_data['liquidity_status']}, "
              f"Regime: {macro_data['regime_state']}")

        if age_hours is not None and age_hours > 28:
            print(f"  [Macro] ⚠️  WARNING: Macro file is {age_hours:.0f}h old — update recommended")

        return macro_data

    # ── Private ───────────────────────────────────────────────────────────────

    def _find_latest_json(self) -> Path | None:
        """Return path of most recently modified macro_intelligence_*.json"""
        if not self.folder.exists():
            return None
        files = list(self.folder.glob('macro_intelligence_*.json'))
        if not files:
            return None
        return max(files, key=lambda p: p.stat().st_mtime)

    def _validate(self, data: dict) -> list[str]:
        """Return list of validation error strings. Empty list = valid."""
        errors = []

        # Required fields present
        for field in REQUIRED_FIELDS:
            if field not in data:
                errors.append(f"Missing required field: '{field}'")

        if errors:
            return errors  # Don't continue — values may be missing

        # Enum validation
        for field, valid_set in VALID_VALUES.items():
            if field == 'sector_bias_values':
                continue  # Handled separately below
            if field in data:
                val = data[field]
                if val not in valid_set:
                    errors.append(
                        f"'{field}' = '{val}' is not valid. "
                        f"Valid values: {sorted(valid_set)}"
                    )

        # conviction_score range
        cs = data.get('conviction_score')
        if cs is not None:
            try:
                cs = float(cs)
                if not (0.0 <= cs <= 1.0):
                    errors.append(f"'conviction_score' must be 0.0–1.0, got {cs}")
            except (TypeError, ValueError):
                errors.append(f"'conviction_score' must be a number, got {cs!r}")

        # vix_contango type
        vc = data.get('vix_contango')
        if vc is not None:
            try:
                float(vc)
            except (TypeError, ValueError):
                errors.append(f"'vix_contango' must be a number, got {vc!r}")

        # sector_bias values
        sb = data.get('sector_bias')
        if sb is not None:
            if not isinstance(sb, dict):
                errors.append("'sector_bias' must be a dict, e.g. {\"TECH\": \"AVOID\"}")
            else:
                valid_sb = VALID_VALUES['sector_bias_values']
                for sector, bias in sb.items():
                    if bias not in valid_sb:
                        errors.append(
                            f"sector_bias['{sector}'] = '{bias}' is not valid. "
                            f"Valid: {sorted(valid_sb)}"
                        )

        # report_date format
        rd = data.get('report_date', '')
        try:
            datetime.strptime(rd, '%Y-%m-%d')
        except ValueError:
            errors.append(f"'report_date' must be YYYY-MM-DD, got '{rd}'")

        return errors

    def _normalise(self, data: dict) -> dict:
        """
        Return clean, typed dict with all fields options_intelligence
        and VANGUARD expect. Adds risk_on_prob alias for conviction_score.
        """
        cs = float(data['conviction_score'])

        # Map conviction_score → macro_conviction label if not set
        if 'macro_conviction' not in data:
            if cs >= 0.70:
                macro_conviction = 'High'
            elif cs >= 0.55:
                macro_conviction = 'Medium'
            else:
                macro_conviction = 'Low'
        else:
            macro_conviction = data['macro_conviction']

        return {
            # Metadata
            'as_of_utc':           data['as_of_utc'],
            'report_date':         data['report_date'],

            # Regime — options_intelligence fields
            'risk_on_switch':      data['risk_on_switch'],
            'conviction_score':    cs,
            'risk_on_prob':        cs,          # alias used by options_intelligence
            'liquidity_status':    data['liquidity_status'],
            'volatility_mode':     data['volatility_mode'],
            'vix_contango':        float(data['vix_contango']),

            # Regime — VANGUARD fields
            'regime_state':        data['regime_state'],
            'dir_bias':            data['dir_bias'],
            'regime_drift_status': data['regime_drift_status'],
            'macro_conviction':    macro_conviction,

            # Optional
            'sector_bias':         data.get('sector_bias', {}),
            'notes':               data.get('notes', ''),
        }

    def _age_hours(self, as_of_utc: str) -> float | None:
        """Return age of macro data in hours, or None if unparseable."""
        try:
            dt = datetime.fromisoformat(as_of_utc.replace('Z', '+00:00'))
            now = datetime.now(timezone.utc)
            return (now - dt).total_seconds() / 3600
        except Exception:
            return None
