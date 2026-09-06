"""
AVSHUNTER Data Collector
Collects CSVs, charts, and screenshots from data folder
"""
import os
import json
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Tuple

class DataCollector:
    def __init__(self, config_path: str = "config/settings.json"):
        with open(config_path, 'r') as f:
            self.config = json.load(f)
        
        self.base_dir = Path(self.config['data_paths']['base_dir'])
        self.today = datetime.now().strftime("%Y-%m-%d")
        self.data_dir = self.base_dir / self.today
        
    def get_today_folder(self) -> Path:
        """Get or create today's data folder"""
        self.data_dir.mkdir(parents=True, exist_ok=True)
        (self.data_dir / "csvs").mkdir(exist_ok=True)
        (self.data_dir / "charts").mkdir(exist_ok=True)
        (self.data_dir / "screenshots").mkdir(exist_ok=True)
        return self.data_dir
    
    def check_data_ready(self) -> Tuple[bool, Dict]:
        """Check if all required data is present"""
        status = {
            'csvs': [],
            'charts': [],
            'screenshots': [],
            'missing': [],
            'ready': False
        }
        
        # Check CSVs
        csv_dir = self.data_dir / "csvs"
        if csv_dir.exists():
            status['csvs'] = [f.name for f in csv_dir.glob("*.csv")]
        
        # Check charts
        chart_dir = self.data_dir / "charts"
        if chart_dir.exists():
            status['charts'] = [f.name for f in chart_dir.glob("*.png")]
        
        # Check screenshots
        screenshot_dir = self.data_dir / "screenshots"
        if screenshot_dir.exists():
            status['screenshots'] = [f.name for f in screenshot_dir.glob("*.png")]
        
        # Determine if ready
        min_screenshots = self.config['expected_files']['screenshots_min']
        has_data = len(status['csvs']) > 0
        has_charts = len(status['charts']) > 0
        has_screenshots = len(status['screenshots']) >= min_screenshots
        
        status['ready'] = has_data and has_screenshots
        
        if not has_data:
            status['missing'].append(f"CSVs (found {len(status['csvs'])})")
        if not has_charts:
            status['missing'].append(f"Charts (found {len(status['charts'])})")
        if not has_screenshots:
            status['missing'].append(
                f"Screenshots (need {min_screenshots}, found {len(status['screenshots'])})"
            )
        
        return status['ready'], status
    
    def collect_all_data(self) -> Dict:
        """Collect all data files for processing"""
        data = {
            'csvs': [],
            'charts': [],
            'screenshots': [],
            'date': self.today
        }
        
        # Collect CSVs
        csv_dir = self.data_dir / "csvs"
        for csv_file in csv_dir.glob("*.csv"):
            data['csvs'].append({
                'name': csv_file.name,
                'path': str(csv_file),
                'size': csv_file.stat().st_size
            })
        
        # Collect charts
        chart_dir = self.data_dir / "charts"
        for chart_file in chart_dir.glob("*.png"):
            data['charts'].append({
                'name': chart_file.name,
                'path': str(chart_file),
                'size': chart_file.stat().st_size
            })
        
        # Collect screenshots
        screenshot_dir = self.data_dir / "screenshots"
        for screenshot in screenshot_dir.glob("*.png"):
            data['screenshots'].append({
                'name': screenshot.name,
                'path': str(screenshot),
                'size': screenshot.stat().st_size
            })
        
        return data
    
    def get_summary(self) -> str:
        """Get human-readable summary"""
        _, status = self.check_data_ready()
        
        summary = f"Data Collection Status ({self.today}):\n"
        summary += f"  CSVs: {len(status['csvs'])} files\n"
        summary += f"  Charts: {len(status['charts'])} files\n"
        summary += f"  Screenshots: {len(status['screenshots'])} files\n"
        summary += f"  Ready: {'âœ“ YES' if status['ready'] else 'âœ— NO'}\n"
        
        if status['missing']:
            summary += f"  Missing: {', '.join(status['missing'])}\n"
        
        return summary
