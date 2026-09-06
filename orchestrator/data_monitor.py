from pathlib import Path

class DataMonitor:
    def __init__(self, data_path, config):
        self.data_path = Path(data_path)
        self.config = config
        
        # Expected folders
        self.csvs_folder = self.data_path / config['data_paths']['csvs_folder']
        self.charts_folder = self.data_path / config['data_paths']['charts_folder']
        self.screenshots_folder = self.data_path / config['data_paths']['screenshots_folder']
    
    def check_status(self):
        """Check what files are available"""
        
        # Get all files
        csvs = list(self.csvs_folder.glob('*.csv')) if self.csvs_folder.exists() else []
        charts = list(self.charts_folder.glob('*.png')) + list(self.charts_folder.glob('*.jpg')) if self.charts_folder.exists() else []
        screenshots = list(self.screenshots_folder.glob('*.png')) + list(self.screenshots_folder.glob('*.jpg')) if self.screenshots_folder.exists() else []
        
        # Check requirements
        min_screenshots = self.config['expected_files']['screenshots_min']
        
        has_csvs = len(csvs) > 0
        has_charts = len(charts) > 0
        has_screenshots = len(screenshots) >= min_screenshots
        
        # Ready if all requirements met
        ready = has_csvs and has_screenshots
        
        return {
            'ready': ready,
            'csvs': csvs,
            'charts': charts,
            'screenshots': screenshots,
            'csvs_count': len(csvs),
            'charts_count': len(charts),
            'screenshots_count': len(screenshots),
            'has_csvs': has_csvs,
            'has_charts': has_charts,
            'has_screenshots': has_screenshots
        }

