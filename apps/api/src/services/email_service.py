"""
Email Service for sending transactional emails.

Uses Gmail SMTP for password reset and notifications.
"""

import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Optional
import structlog

from ..core.config import get_settings

logger = structlog.get_logger(__name__)


class EmailService:
    """Service for sending emails via Gmail SMTP."""

    def __init__(self):
        self.settings = get_settings()
        self.smtp_host = "smtp.gmail.com"
        self.smtp_port = 587
        self.from_email = self.settings.smtp_from_email or "support@saptiva.com"
        self.smtp_user = self.settings.smtp_user
        self.smtp_password = self.settings.smtp_password

    def _create_smtp_connection(self):
        """Create and return SMTP connection."""
        try:
            server = smtplib.SMTP(self.smtp_host, self.smtp_port)
            server.starttls()
            server.login(self.smtp_user, self.smtp_password)
            return server
        except Exception as e:
            logger.error(
                "Failed to connect to SMTP server",
                error=str(e),
                exc_type=type(e).__name__
            )
            raise

    async def send_email(
        self,
        to_email: str,
        subject: str,
        html_body: str,
        text_body: Optional[str] = None
    ) -> bool:
        """
        Send email via Gmail SMTP.

        Args:
            to_email: Recipient email address
            subject: Email subject
            html_body: HTML email body
            text_body: Plain text fallback (optional)

        Returns:
            True if email sent successfully, False otherwise
        """
        try:
            # Create message
            msg = MIMEMultipart("alternative")
            msg["Subject"] = subject
            msg["From"] = f"Saptiva Support <{self.from_email}>"
            msg["To"] = to_email

            # Add plain text version if provided
            if text_body:
                part1 = MIMEText(text_body, "plain")
                msg.attach(part1)

            # Add HTML version
            part2 = MIMEText(html_body, "html")
            msg.attach(part2)

            # Send email
            with self._create_smtp_connection() as server:
                server.send_message(msg)

            logger.info(
                "Email sent successfully",
                to=to_email,
                subject=subject
            )
            return True

        except Exception as e:
            logger.error(
                "Failed to send email",
                to=to_email,
                subject=subject,
                error=str(e),
                exc_type=type(e).__name__
            )
            return False

    async def send_password_reset_email(
        self,
        to_email: str,
        username: str,
        reset_link: str
    ) -> bool:
        """
        Send password reset email.

        Args:
            to_email: User's email address
            username: User's name
            reset_link: Password reset link with token

        Returns:
            True if email sent successfully
        """
        subject = "Recuperación de Contraseña - Saptiva"

        html_body = f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
            line-height: 1.6;
            color: #333;
            max-width: 600px;
            margin: 0 auto;
            padding: 20px;
        }}
        .container {{
            background-color: #ffffff;
            border-radius: 8px;
            padding: 30px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }}
        .header {{
            text-align: center;
            margin-bottom: 30px;
        }}
        .logo {{
            font-size: 24px;
            font-weight: bold;
            color: #4F46E5;
        }}
        .button {{
            display: inline-block;
            padding: 12px 24px;
            background-color: #4F46E5;
            color: #ffffff !important;
            text-decoration: none;
            border-radius: 6px;
            font-weight: 500;
            margin: 20px 0;
        }}
        .button:hover {{
            background-color: #4338CA;
        }}
        .footer {{
            margin-top: 30px;
            padding-top: 20px;
            border-top: 1px solid #E5E7EB;
            font-size: 14px;
            color: #6B7280;
        }}
        .warning {{
            background-color: #FEF3C7;
            border-left: 4px solid #F59E0B;
            padding: 12px;
            margin: 20px 0;
            border-radius: 4px;
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <div class="logo">🤖 Saptiva</div>
            <h2 style="color: #1F2937; margin-top: 10px;">Recuperación de Contraseña</h2>
        </div>

        <p>Hola <strong>{username}</strong>,</p>

        <p>Recibimos una solicitud para restablecer la contraseña de tu cuenta de Saptiva.</p>

        <p>Para crear una nueva contraseña, haz clic en el siguiente botón:</p>

        <div style="text-align: center;">
            <a href="{reset_link}" class="button">Restablecer Contraseña</a>
        </div>

        <div class="warning">
            <strong>⚠️ Importante:</strong> Este enlace es válido solo por <strong>1 hora</strong>.
        </div>

        <p>Si no solicitaste restablecer tu contraseña, puedes ignorar este correo de forma segura.</p>

        <p>O copia y pega este enlace en tu navegador:</p>
        <p style="background-color: #F3F4F6; padding: 10px; border-radius: 4px; word-break: break-all; font-size: 12px;">
            {reset_link}
        </p>

        <div class="footer">
            <p>Saludos,<br>El equipo de <strong>Saptiva</strong></p>
            <p style="font-size: 12px; color: #9CA3AF;">
                Este es un correo automático, por favor no respondas a este mensaje.
            </p>
        </div>
    </div>
</body>
</html>
"""

        text_body = f"""
Hola {username},

Recibimos una solicitud para restablecer la contraseña de tu cuenta de Saptiva.

Para crear una nueva contraseña, visita el siguiente enlace:
{reset_link}

IMPORTANTE: Este enlace es válido solo por 1 hora.

Si no solicitaste restablecer tu contraseña, puedes ignorar este correo de forma segura.

Saludos,
El equipo de Saptiva

---
Este es un correo automático, por favor no respondas a este mensaje.
"""

        return await self.send_email(
            to_email=to_email,
            subject=subject,
            html_body=html_body,
            text_body=text_body
        )


# Singleton instance
_email_service: Optional[EmailService] = None


def get_email_service() -> EmailService:
    """Get email service singleton."""
    global _email_service
    if _email_service is None:
        _email_service = EmailService()
    return _email_service
