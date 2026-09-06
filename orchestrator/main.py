import json
import os
import time
from pathlib import Path
from datetime import datetime
from .data_monitor import DataMonitor
from .claude_api import ClaudeIntelligence
from .report_generator import ReportGenerator
from .email_sender import EmailSender

import logging
import sys

logger = logging.getLogger(__name__)

def _ensure_utf8_stdout() -> None:
    """Best-effort: make Windows consoles behave (so unicode logs don't crash)."""
    try:
        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

def _safe_print(msg: str) -> None:
    """Print that won't crash if the console encoding can't render unicode."""
    try:
        print(msg)
    except UnicodeEncodeError:
        safe = msg.encode("utf-8", "backslashreplace").decode("ascii", "ignore")
        print(safe)

_ensure_utf8_stdout()

class AVSHUNTEROrchestrator:
    def __init__(self, config_path='config/settings.json', session=''):
        # Load config
        with open(config_path, 'r', encoding='utf-8') as f:
            self.config = json.load(f)

        # Optional: Context (pinned artefacts) injected by upstream PREP/OPS wrapper
        # If AVSHUNTER_CONTEXT_DIR is set, we expose pinned paths via env vars for downstream modules.
        self.context_dir = None
        self.pinned_macro = None
        self.pinned_universe = None

        ctx = os.environ.get("AVSHUNTER_CONTEXT_DIR", "").strip()
        if ctx:
            p = Path(ctx)
            if p.exists() and p.is_dir():
                self.context_dir = p
                macro = p / "macro_snapshot.json"
                uni = p / "clean_universe__with_sector.csv"
                if macro.exists():
                    self.pinned_macro = macro
                    os.environ["AVSHUNTER_MACRO_PATH"] = str(macro)
                if uni.exists():
                    self.pinned_universe = uni
                    os.environ["AVSHUNTER_UNIVERSE_PATH"] = str(uni)

        self.session = session
        self.today = datetime.now().strftime('%Y-%m-%d')

        # Build data path with optional session
        if session:
            self.data_path = Path(self.config['data_paths']['base_dir']) / self.today / session
        else:
            self.data_path = Path(self.config['data_paths']['base_dir']) / self.today

        # Initialize components
        self.claude = ClaudeIntelligence(config_path=config_path)
        self.monitor = DataMonitor(str(self.data_path), self.config)
        self.report_gen = ReportGenerator(self.config)
        self.email = EmailSender(self.config)
        self.options = None  # optional, lazy-loaded
        self._init_options_intelligence_if_enabled()
        print(f"Date: {self.today}")
        if session:
            print(f"Session: {session.upper()}")
        print(f"Mode: {self.config['orchestrator']['mode'].title()}")
        if self.context_dir:
            print(f"Context: {self.context_dir}")
            if self.pinned_macro:
                print(f"  Pinned macro: {self.pinned_macro.name}")
            if self.pinned_universe:
                print(f"  Pinned universe: {self.pinned_universe.name}")



    def _init_options_intelligence_if_enabled(self) -> None:
        """Options Intelligence is optional; import lazily so it can't break core runs."""
        try:
            features = self.config.get("features", {}) if isinstance(self.config, dict) else {}
            oi_cfg = features.get("options_intelligence", {}) if isinstance(features, dict) else {}
            enabled = bool(oi_cfg.get("enabled", False))

            env = os.getenv("AVS_ENABLE_OPTIONS", "").strip().lower()
            if env in {"1", "true", "yes", "y", "on"}:
                enabled = True
            if env in {"0", "false", "no", "n", "off"}:
                enabled = False

            if not enabled:
                logger.info("Options Intelligence: disabled (skipping).")
                return

            from .options_intelligence import OptionsIntelligence  # local import by design
            self.options = OptionsIntelligence()
            logger.info("Options Intelligence: enabled (loaded).")
        except Exception as e:
            self.options = None
            logger.warning(f"Options Intelligence: failed to load (skipping). Reason: {e}")

    def run(self):
        mode = self.config['orchestrator']['mode']

        if mode == 'monitor':
            self._run_monitor_mode()
        elif mode == 'immediate':
            self._run_immediate_mode()
        else:
            raise ValueError(f"Unknown mode: {mode}")

    def _run_monitor_mode(self):
        """Wait for files, then process"""
        print(f"[{datetime.now().strftime('%H:%M:%S')}] Waiting for data...")
        print(f"Data folder: {self.data_path}")

        timeout = self.config['monitoring']['timeout_minutes'] * 60
        interval = self.config['monitoring']['check_interval_seconds']
        elapsed = 0

        while elapsed < timeout:
            status = self.monitor.check_status()

            print(f"[{datetime.now().strftime('%H:%M:%S')}] Status:")
            print(f"  CSVs: {status['csvs_count']}")
            print(f"  Screenshots: {status['screenshots_count']}")

            if not status['ready']:
                missing = []
                if not status['has_csvs']:
                    missing.append(f"CSVs (found {status['csvs_count']})")
                if not status['has_charts']:
                    missing.append(f"Charts (found {status['charts_count']})")
                if not status['has_screenshots']:
                    missing.append(f"Screenshots (need {self.config['expected_files']['screenshots_min']}, found {status['screenshots_count']})")

                print(f"  Waiting for: {', '.join(missing)}")
                time.sleep(interval)
                elapsed += interval
                continue

            # Data is ready!
            print(f"\nâœ… All data ready! Processing...")
            self._process_data(status)
            return

        print(f"\nâ° Timeout reached ({self.config['monitoring']['timeout_minutes']} minutes)")

    def _run_immediate_mode(self):
        """Process data immediately, but honour governance gates."""
        status = self.monitor.check_status()

        # Governance: fail-closed by default in immediate mode.
        # You can loosen this only intentionally via config:
        #   orchestrator.immediate_allow_incomplete = true
        #   orchestrator.immediate_discovery_only = true  (allows zero-input runs, but flags them)
        orch_cfg = self.config.get('orchestrator', {})
        allow_incomplete = bool(orch_cfg.get('immediate_allow_incomplete', False))
        discovery_only = bool(orch_cfg.get('immediate_discovery_only', False))

        csvs_n = status.get('csvs_count', 0)
        charts_n = status.get('charts_count', 0)
        shots_n = status.get('screenshots_count', 0)

        # Zero-input runs are epistemically worthless for execution-grade processing.
        if csvs_n == 0 and charts_n == 0 and shots_n == 0:
            if discovery_only:
                print("âš ï¸ Zero inputs detected â€” DISCOVERY_ONLY (immediate mode). No execution-grade outputs should be trusted.")
            else:
                raise RuntimeError("BLOCKED: Zero inputs (CSVs=0, Charts=0, Screenshots=0). Run refresh + monitor mode, or enable orchestrator.immediate_discovery_only intentionally.")

        if not status.get('ready', False) and not allow_incomplete:
            # If partially incomplete, block unless explicitly allowed.
            missing = []
            if not status.get('has_csvs', False):
                missing.append(f"CSVs (found {csvs_n})")
            if not status.get('has_charts', False):
                missing.append(f"Charts (found {charts_n})")
            if not status.get('has_screenshots', False):
                missing.append(f"Screenshots (found {shots_n})")
            raise RuntimeError("BLOCKED: Data incomplete in immediate mode: " + ", ".join(missing) +
                               ". Use monitor mode or set orchestrator.immediate_allow_incomplete=true.")

        if not status.get('ready', False) and allow_incomplete:
            print("âš ï¸ Data incomplete, processing anyway (immediate mode, allow_incomplete=true)")

        self._process_data(status)

    def _process_data(self, status):
        """Run Claude analysis and generate report"""
        print("\n" + "="*60)
        print("PROCESSING DATA")
        print("="*60)

        # Get file lists
        csvs = status['csvs']
        charts = status['charts']
        screenshots = status['screenshots']

        print(f"\nðŸ“Š Analyzing with Claude API...")
        print(f"  - CSVs: {len(csvs)}")
        print(f"  - Charts: {len(charts)}")
        print(f"  - Screenshots: {len(screenshots)}")

        # Call Claude for Macro Analysis
        print("\nðŸ” Running Macro Module...")
        macro_analysis = self.claude.analyze_macro(csvs, charts + screenshots)

        # Call Claude for Futures Bias
        print("ðŸ” Running Futures Bias Module...")
        futures_analysis = self.claude.analyze_futures(csvs, charts + screenshots)

        # NEW: Call Options Intelligence
        print("\nðŸ” Running Options Intelligence Module...")
        options_analysis = None
        if getattr(self, "options", None) is not None:
            options_analysis = self.options.scan_options()
        else:
            logger.info("Options Intelligence: skipped (not loaded).")

        # Generate Report
        print("\nðŸ“„ Generating PDF report...")
        session_label = f" - {self.session.upper()}" if self.session else ""
        report_path = self.report_gen.generate(
            macro_analysis=macro_analysis,
            futures_analysis=futures_analysis,
            options_analysis=options_analysis,
            date=self.today,
            session=self.session
        )

        print(f"âœ… Report saved: {report_path}")

        # Send Email
        if self.config['email']['enabled']:
            print("\nðŸ“§ Sending email...")
            subject = self.config['email']['subject_template'].format(date=self.today) + session_label
            self.email.send(
                subject=subject,
                body=f"AVSHUNTER Intelligence Report{session_label}\nDate: {self.today}",
                attachments=[report_path]
            )
            print("âœ… Email sent!")

        print("\n" + "="*60)
        print("âœ… PROCESSING COMPLETE")
        print("="*60)
