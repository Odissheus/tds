"""
Email Agent — sends reports and alerts via SendGrid.
"""
import logging
import os
from datetime import datetime, timezone

from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import (
    Attachment,
    ContentId,
    Disposition,
    FileContent,
    FileName,
    FileType,
    Mail,
    To,
)
import base64

from backend.config import settings

logger = logging.getLogger("tds.agent.email")


def send_weekly_report(pdf_path: str, week: str, highlights: list) -> bool:
    """Send the weekly report email with PDF attachment."""
    now = datetime.now(timezone.utc)
    iso_year, iso_week = week.split("-W")

    from datetime import date, timedelta

    monday = date.fromisocalendar(int(iso_year), int(iso_week), 1)
    sunday = monday + timedelta(days=6)

    monday_str = monday.strftime("%d %b")
    sunday_str = sunday.strftime("%d %b %Y")
    week_num = iso_week

    subject = f"📱 TDS Report Pixel | Week {week_num} — {monday_str} › {sunday_str}"

    highlights_html = ""
    for i, h in enumerate(highlights[:3], 1):
        highlights_html += f"<li style='margin-bottom:8px;'>{h}</li>"

    body_html = f"""
    <div style="font-family: 'Roboto', Arial, sans-serif; max-width: 600px; margin: 0 auto;">
        <div style="background: #4285F4; padding: 20px; text-align: center; border-radius: 8px 8px 0 0;">
            <h1 style="color: white; margin: 0; font-size: 24px;">TDS — Tech Deep Search</h1>
            <p style="color: rgba(255,255,255,0.8); margin: 5px 0 0;">© React SRL</p>
        </div>

        <div style="background: white; padding: 30px; border: 1px solid #e0e0e0;">
            <h2 style="color: #333; margin-top: 0;">📱 Report Settimanale Pixel</h2>
            <p style="color: #666;">Settimana {week_num} — {monday_str} › {sunday_str}</p>

            <div style="background: #f8f9fa; padding: 20px; border-radius: 8px; margin: 20px 0;">
                <h3 style="color: #4285F4; margin-top: 0;">🔝 Top 3 Highlights</h3>
                <ol style="color: #333; padding-left: 20px;">
                    {highlights_html}
                </ol>
            </div>

            <p style="color: #666; font-size: 14px;">
                Il report completo è in allegato come PDF.<br>
                Puoi anche consultare la dashboard per i dati live.
            </p>
        </div>

        <div style="background: #f5f5f5; padding: 15px; text-align: center; border-radius: 0 0 8px 8px; border: 1px solid #e0e0e0; border-top: none;">
            <p style="color: #999; font-size: 12px; margin: 0;">
                TDS Tech Deep Search — React SRL<br>
                Report generato automaticamente | Dati: Euronics, Unieuro, MediaWorld
            </p>
        </div>
    </div>
    """

    pdf_filename = f"TDS_PixelReport_{now.strftime('%Y-%m-%d')}.pdf"

    return _send_email(
        subject=subject,
        html_content=body_html,
        attachment_path=pdf_path,
        attachment_name=pdf_filename,
    )


async def send_alert_email(subject: str, body: str) -> bool:
    """Send an alert email."""
    html_content = f"""
    <div style="font-family: 'Roboto', Arial, sans-serif; max-width: 600px; margin: 0 auto;">
        <div style="background: #EA4335; padding: 15px; text-align: center; border-radius: 8px 8px 0 0;">
            <h2 style="color: white; margin: 0;">TDS — Tech Deep Search | Alert</h2>
        </div>
        <div style="background: white; padding: 25px; border: 1px solid #e0e0e0;">
            {body}
        </div>
        <div style="background: #f5f5f5; padding: 10px; text-align: center; border-radius: 0 0 8px 8px;">
            <p style="color: #999; font-size: 11px; margin: 0;">TDS Tech Deep Search — React SRL</p>
        </div>
    </div>
    """
    return _send_email(subject=subject, html_content=html_content)


def _send_email(
    subject: str,
    html_content: str,
    attachment_path: str = None,
    attachment_name: str = None,
) -> bool:
    """Send email via SendGrid."""
    if not settings.SENDGRID_API_KEY:
        logger.warning("SENDGRID_API_KEY not set, skipping email send")
        return False

    try:
        message = Mail(
            from_email=(settings.EMAIL_FROM, settings.EMAIL_FROM_NAME),
            to_emails=[To(email) for email in settings.EMAIL_TO],
            subject=subject,
            html_content=html_content,
        )

        if attachment_path and os.path.exists(attachment_path):
            with open(attachment_path, "rb") as f:
                pdf_data = f.read()

            attachment = Attachment(
                FileContent(base64.b64encode(pdf_data).decode()),
                FileName(attachment_name or "report.pdf"),
                FileType("application/pdf"),
                Disposition("attachment"),
            )
            message.attachment = attachment

        sg = SendGridAPIClient(settings.SENDGRID_API_KEY)
        response = sg.send(message)

        logger.info(
            "Email sent: %s (status: %d, recipients: %s)",
            subject,
            response.status_code,
            ", ".join(settings.EMAIL_TO),
        )
        return response.status_code in (200, 201, 202)

    except Exception as e:
        logger.error("Failed to send email: %s", str(e))
        return False
