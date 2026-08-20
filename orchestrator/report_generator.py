from pathlib import Path
from datetime import datetime
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, PageBreak
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch

class ReportGenerator:
    def __init__(self, config):
        self.config = config

    def generate(self, macro_analysis, futures_analysis, options_analysis, date, session=''):
        '''Generate PDF report'''
        # Create reports folder if not exists
        reports_dir = Path('reports')
        reports_dir.mkdir(exist_ok=True)

        # Build filename
        session_suffix = f"_{session}" if session else ""
        filename = f"AVSHUNTER_Intelligence_{date}{session_suffix}.pdf"
        output_path = reports_dir / filename

        # Create PDF
        doc = SimpleDocTemplate(str(output_path), pagesize=letter)
        story = []
        styles = getSampleStyleSheet()

        # Title
        title_style = ParagraphStyle(
            'CustomTitle',
            parent=styles['Heading1'],
            fontSize=24,
            textColor='#1a1a1a',
            spaceAfter=30,
        )

        session_label = f" - {session.upper()}" if session else ""
        title = Paragraph(f"AVSHUNTER Intelligence Report{session_label}", title_style)
        story.append(title)

        date_text = Paragraph(f"<b>Date:</b> {date}", styles['Normal'])
        story.append(date_text)
        story.append(Spacer(1, 0.5*inch))

        # Macro Analysis Section
        story.append(Paragraph("<b>MACRO MODULE ANALYSIS</b>", styles['Heading2']))
        story.append(Spacer(1, 0.2*inch))

        for line in macro_analysis.split('\n'):
            if line.strip():
                story.append(Paragraph(line, styles['Normal']))
                story.append(Spacer(1, 0.1*inch))

        story.append(PageBreak())

        # Futures Bias Section
        story.append(Paragraph("<b>FUTURES BIAS ANALYSIS</b>", styles['Heading2']))
        story.append(Spacer(1, 0.2*inch))

        for line in futures_analysis.split('\n'):
            if line.strip():
                story.append(Paragraph(line, styles['Normal']))
                story.append(Spacer(1, 0.1*inch))

        story.append(PageBreak())

        # NEW: Options Intelligence Section
        story.append(Paragraph("<b>OPTIONS INTELLIGENCE</b>", styles['Heading2']))
        story.append(Spacer(1, 0.2*inch))

        if options_analysis['status'] == 'error':
            story.append(Paragraph(f"<i>Error: {options_analysis['message']}</i>", styles['Normal']))
        else:
            signal_count = options_analysis['signal_count']
            story.append(Paragraph(f"<b>Signals Detected:</b> {signal_count}", styles['Normal']))
            story.append(Spacer(1, 0.2*inch))

            if signal_count > 0:
                story.append(Paragraph("<b>Qualifying Opportunities:</b>", styles['Normal']))
                story.append(Spacer(1, 0.1*inch))
                
                for i, signal in enumerate(options_analysis['signals'], 1):
                    story.append(Paragraph(f"{i}. {signal}", styles['Normal']))
                    story.append(Spacer(1, 0.1*inch))
            else:
                story.append(Paragraph("<i>No qualifying signals found. All tickers scanned with 15-filter criteria.</i>", styles['Normal']))

        # Build PDF
        doc.build(story)

        return str(output_path)
