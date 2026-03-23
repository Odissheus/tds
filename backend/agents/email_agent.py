"""
Email Agent — sends reports and alerts via SendGrid.
Professional HTML email templates with React SRL branding.
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

    subject = f"TDS Weekly Report — W{week_num} | Google Pixel Italia | React SRL"

    # Build highlight cards HTML
    highlights_html = ""
    for i, h in enumerate(highlights[:3], 1):
        highlights_html += f"""
        <tr>
            <td style="padding: 6px 0;">
                <table cellpadding="0" cellspacing="0" border="0" width="100%" style="background: #EFF6FF; border-radius: 8px; border: 1px solid #BFDBFE;">
                    <tr>
                        <td style="padding: 12px 16px;">
                            <table cellpadding="0" cellspacing="0" border="0" width="100%">
                                <tr>
                                    <td width="36" style="vertical-align: top;">
                                        <div style="width: 28px; height: 28px; background: #2563EB; color: white; border-radius: 50%; text-align: center; line-height: 28px; font-weight: 700; font-size: 14px;">{i}</div>
                                    </td>
                                    <td style="padding-left: 12px; font-size: 14px; color: #1E293B; line-height: 1.5;">
                                        {h}
                                    </td>
                                </tr>
                            </table>
                        </td>
                    </tr>
                </table>
            </td>
        </tr>
        """

    body_html = f"""
    <!DOCTYPE html>
    <html>
    <head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1.0"></head>
    <body style="margin: 0; padding: 0; background: #F1F5F9; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
        <table cellpadding="0" cellspacing="0" border="0" width="100%" style="background: #F1F5F9;">
            <tr><td align="center" style="padding: 24px 16px;">
                <table cellpadding="0" cellspacing="0" border="0" width="600" style="max-width: 600px; background: #FFFFFF; border-radius: 12px; overflow: hidden; box-shadow: 0 2px 8px rgba(0,0,0,0.06);">

                    <!-- Header -->
                    <tr>
                        <td style="background: #2563EB; padding: 28px 32px; text-align: center;">
                            <h1 style="color: #FFFFFF; margin: 0; font-size: 22px; font-weight: 700; letter-spacing: -0.3px;">TDS — Tech Deep Search</h1>
                            <p style="color: rgba(255,255,255,0.8); margin: 6px 0 0; font-size: 13px;">React SRL | Google Pixel Price Intelligence</p>
                        </td>
                    </tr>

                    <!-- Period bar -->
                    <tr>
                        <td style="background: #1E40AF; padding: 10px 32px; text-align: center;">
                            <span style="color: rgba(255,255,255,0.9); font-size: 12px; font-weight: 500;">Settimana W{week_num} &mdash; {monday_str} &ndash; {sunday_str}</span>
                        </td>
                    </tr>

                    <!-- Body -->
                    <tr>
                        <td style="padding: 32px;">
                            <p style="color: #1E293B; font-size: 15px; margin: 0 0 8px; font-weight: 600;">Buongiorno,</p>
                            <p style="color: #64748B; font-size: 14px; margin: 0 0 24px; line-height: 1.5;">
                                Ecco i <strong style="color: #2563EB;">3 highlights</strong> del monitoraggio promozioni della settimana W{week_num}:
                            </p>

                            <!-- Highlights -->
                            <table cellpadding="0" cellspacing="0" border="0" width="100%">
                                {highlights_html}
                            </table>

                            <!-- Divider -->
                            <table cellpadding="0" cellspacing="0" border="0" width="100%" style="margin: 24px 0;">
                                <tr><td style="border-top: 1px solid #E2E8F0;"></td></tr>
                            </table>

                            <p style="color: #64748B; font-size: 13px; margin: 0 0 20px; line-height: 1.6;">
                                In allegato trovi il <strong>report PDF completo</strong> con la griglia prezzi Pixel 10 e Pixel 9,
                                il benchmark competitor e le insight strategiche AI.
                            </p>

                            <!-- CTA Button -->
                            <table cellpadding="0" cellspacing="0" border="0" width="100%">
                                <tr>
                                    <td align="center" style="padding: 8px 0 16px;">
                                        <table cellpadding="0" cellspacing="0" border="0">
                                            <tr>
                                                <td style="background: #2563EB; border-radius: 8px; padding: 12px 28px;">
                                                    <span style="color: #FFFFFF; font-size: 14px; font-weight: 600; text-decoration: none;">
                                                        📄 Report PDF in allegato
                                                    </span>
                                                </td>
                                            </tr>
                                        </table>
                                    </td>
                                </tr>
                            </table>
                        </td>
                    </tr>

                    <!-- Footer -->
                    <tr>
                        <td style="background: #F8FAFC; padding: 20px 32px; border-top: 1px solid #E2E8F0; text-align: center;">
                            <p style="color: #94A3B8; font-size: 11px; margin: 0; line-height: 1.6;">
                                <strong>React Tech Monitor</strong> | React SRL<br>
                                TDS — Tech Deep Search | Report automatico settimanale<br>
                                Dati: Amazon, Euronics, Unieuro, MediaWorld
                            </p>
                        </td>
                    </tr>

                </table>
            </td></tr>
        </table>
    </body>
    </html>
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
    <!DOCTYPE html>
    <html>
    <head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1.0"></head>
    <body style="margin: 0; padding: 0; background: #F1F5F9; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Arial, sans-serif;">
        <table cellpadding="0" cellspacing="0" border="0" width="100%" style="background: #F1F5F9;">
            <tr><td align="center" style="padding: 24px 16px;">
                <table cellpadding="0" cellspacing="0" border="0" width="600" style="max-width: 600px; background: #FFFFFF; border-radius: 12px; overflow: hidden; box-shadow: 0 2px 8px rgba(0,0,0,0.06);">
                    <tr>
                        <td style="background: #DC2626; padding: 20px 32px; text-align: center;">
                            <h2 style="color: #FFFFFF; margin: 0; font-size: 18px; font-weight: 700;">TDS — Tech Deep Search | Alert</h2>
                            <p style="color: rgba(255,255,255,0.8); margin: 4px 0 0; font-size: 12px;">React SRL</p>
                        </td>
                    </tr>
                    <tr>
                        <td style="padding: 28px 32px; color: #1E293B; font-size: 14px; line-height: 1.6;">
                            {body}
                        </td>
                    </tr>
                    <tr>
                        <td style="background: #F8FAFC; padding: 16px 32px; text-align: center; border-top: 1px solid #E2E8F0;">
                            <p style="color: #94A3B8; font-size: 11px; margin: 0;">TDS Tech Deep Search — React SRL</p>
                        </td>
                    </tr>
                </table>
            </td></tr>
        </table>
    </body>
    </html>
    """
    return _send_email(subject=subject, html_content=html_content)


def _send_email(
    subject: str,
    html_content: str,
    attachment_path: str = None,
    attachment_name: str = None,
) -> bool:
    """Send email via SendGrid."""
    # Force re-read env (Celery worker may have stale env from fork)
    api_key = os.environ.get("SENDGRID_API_KEY", "")
    if not api_key:
        for env_path in ["/app/.env", ".env"]:
            if os.path.isfile(env_path):
                try:
                    with open(env_path, "r") as f:
                        for line in f:
                            line = line.strip()
                            if line.startswith("SENDGRID_API_KEY="):
                                api_key = line.split("=", 1)[1].strip().strip("'\"")
                                break
                except Exception:
                    pass
            if api_key:
                break
    if not api_key:
        api_key = settings.SENDGRID_API_KEY
    if not api_key:
        logger.warning("SENDGRID_API_KEY not set (checked env + settings), skipping email")
        return False

    logger.info("Sending email: %s (key present: %s, recipients: %s)",
                subject[:60], bool(api_key), ", ".join(settings.EMAIL_TO))

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

        sg = SendGridAPIClient(api_key)
        response = sg.send(message)

        logger.info(
            "Email sent: %s (status: %d, recipients: %s)",
            subject,
            response.status_code,
            ", ".join(settings.EMAIL_TO),
        )
        return response.status_code in (200, 201, 202)

    except Exception as e:
        logger.error("Failed to send email '%s': %s", subject[:60], str(e))
        return False
