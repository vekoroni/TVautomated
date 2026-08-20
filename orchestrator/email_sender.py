import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.application import MIMEApplication
from pathlib import Path
from dotenv import load_dotenv

class EmailSender:
    def __init__(self, config):
        load_dotenv()
        self.config = config
        
        self.gmail_address = os.getenv('GMAIL_ADDRESS')
        self.gmail_password = os.getenv('GMAIL_APP_PASSWORD')
        self.recipient = os.getenv('RECIPIENT_EMAIL')
    
    def send(self, subject, body, attachments=None):
        """Send email with optional attachments"""
        
        msg = MIMEMultipart()
        msg['From'] = f"{self.config['email']['from_name']} <{self.gmail_address}>"
        msg['To'] = self.recipient
        msg['Subject'] = subject
        
        msg.attach(MIMEText(body, 'plain'))
        
        # Add attachments
        if attachments:
            for filepath in attachments:
                with open(filepath, 'rb') as f:
                    part = MIMEApplication(f.read(), Name=Path(filepath).name)
                    part['Content-Disposition'] = f'attachment; filename="{Path(filepath).name}"'
                    msg.attach(part)
        
        # Send via Gmail SMTP
        with smtplib.SMTP('smtp.gmail.com', 587) as server:
            server.starttls()
            server.login(self.gmail_address, self.gmail_password)
            server.send_message(msg)
