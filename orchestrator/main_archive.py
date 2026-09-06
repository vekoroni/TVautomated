import json
import time
from pathlib import Path
from datetime import datetime
from .data_monitor import DataMonitor
from .claude_api import ClaudeIntelligence
from .report_generator import ReportGenerator
from .email_sender import EmailSender
from .options_intelligence import OptionsIntelligence

class AVSHUNTEROrchestrator:
    def __init__(self, config_path='config/settings.json', session=''):
        # Load config
        with open(config_path, 'r', encoding='utf-8') as f:
            self.config = json.load(f)

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
        self.options = OptionsIntelligence(self.config)

        print(f"Date: {self.today}")
        if session:
            print(f"Session: {session.upper()}")
        print(f"Mode: {self.config['orchestrator']['mode'].title()}")

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
            print(f"\n✅ All data ready! Processing...")
            self._process_data(status)
            return

        print(f"\n⏰ Timeout reached ({self.config['monitoring']['timeout_minutes']} minutes)")

    def _run_immediate_mode(self):
        """Process whatever data exists now"""
        status = self.monitor.check_status()

        if not status['ready']:
            print("⚠️ Data incomplete, processing anyway (immediate mode)")

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

        print(f"\n📊 Analyzing with Claude API...")
        print(f"  - CSVs: {len(csvs)}")
        print(f"  - Charts: {len(charts)}")
        print(f"  - Screenshots: {len(screenshots)}")

        # Call Claude for Macro Analysis
        print("\n🔍 Running Macro Module...")
        macro_analysis = self.claude.analyze_macro(csvs, charts + screenshots)

        # Call Claude for Futures Bias
        print("🔍 Running Futures Bias Module...")
        futures_analysis = self.claude.analyze_futures(csvs, charts + screenshots)

        # NEW: Call Options Intelligence
        print("\n🔍 Running Options Intelligence Module...")
        options_analysis = self.options.scan_options()

        # Generate Report
        print("\n📄 Generating PDF report...")
        session_label = f" - {self.session.upper()}" if self.session else ""
        report_path = self.report_gen.generate(
            macro_analysis=macro_analysis,
            futures_analysis=futures_analysis,
            options_analysis=options_analysis,
            date=self.today,
            session=self.session
        )

        print(f"✅ Report saved: {report_path}")

        # Send Email
        if self.config['email']['enabled']:
            print("\n📧 Sending email...")
            subject = self.config['email']['subject_template'].format(date=self.today) + session_label
            self.email.send(
                subject=subject,
                body=f"AVSHUNTER Intelligence Report{session_label}\nDate: {self.today}",
                attachments=[report_path]
            )
            print("✅ Email sent!")

        print("\n" + "="*60)
        print("✅ PROCESSING COMPLETE")
        print("="*60)

