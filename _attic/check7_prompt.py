import sys
sys.path.insert(0, '.')

from pipeline_interpreter_engine import build_story_prompt, scan_ma_inputs_for_ticker
from thesis_registry import get_active_thesis, get_latest_story_path

TICKER = 'WFC'
ma_files    = scan_ma_inputs_for_ticker(TICKER)
chart_files = ma_files['charts'] + ma_files['screenshots']
opt_files   = ma_files['options']

fake_row = {
    'ticker': TICKER, 'direction': 'LONG_PUT', 'horizon': '11-20',
    'kill_switch_level': '77.50', 'probe_trigger': '75.00',
    'armed_trigger': '74.00', 'triage_verdict': 'PROBE',
}

prompt = build_story_prompt(
    ticker=TICKER,
    pipeline_row=fake_row,
    options_data=None,
    chart_images=chart_files or None,
    update_type='FULL',
)

print('Pipeline row injected:     ' + ('YES' if 'LONG_PUT' in prompt else 'NO'))
print('Macro+delta+news section:  ' + ('YES' if 'MACRO + ENRICHMENT DELTA' in prompt else 'NO'))
print('Live price block:          ' + ('YES' if 'LIVE PRICE' in prompt else 'NO'))
print('update_type=FULL header:   ' + ('YES' if 'update_type: FULL' in prompt else 'NO'))
print('Story instructions block:  ' + ('YES' if 'STORY OF THE TRADE INSTRUCTIONS' in prompt else 'NO'))
print('JUNIOR_BRIEFING tag:       ' + ('YES' if 'JUNIOR_BRIEFING' in prompt else 'NO'))
print('Execution permission lock: ' + ('YES' if 'NONE_PIPELINE_INTERPRETER_ONLY' in prompt else 'NO'))
print('Chart files available:     ' + str(len(chart_files)) + ' files passed to images= arg')
print('Options files available:   ' + str(len(opt_files)) + ' files')
print('Total prompt length:       ' + str(len(prompt)) + ' chars')
active = get_active_thesis(TICKER)
print('Active thesis WFC:         ' + ('NONE' if not active else active.get('thesis_id', '?')))
latest = get_latest_story_path(TICKER)
print('Latest story path:         ' + ('NONE' if not latest else str(latest)))
