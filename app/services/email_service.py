"""Email service with SMTP support and mock fallback for development."""
import logging
import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Optional

from sqlalchemy.orm import Session

from app.models.listing import Listing
from app.models.user_email_preference import ListingNotificationSent, UserEmailPreference

logger = logging.getLogger(__name__)

SMTP_HOST = os.getenv("SMTP_HOST", "localhost")
SMTP_PORT = int(os.getenv("SMTP_PORT", "1025"))
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_PASS = os.getenv("SMTP_PASS", "")
SENDER_EMAIL = os.getenv("SENDER_EMAIL", "noreply@emlakai.com")
MOCK_MODE = os.getenv("MOCK_EMAIL", "true").lower() in ("true", "1", "yes")


def send_email(to_email: str, subject: str, html_body: str) -> bool:
    """Send an email via SMTP or mock (for development)."""
    if MOCK_MODE:
        logger.info(f"[MOCK EMAIL] To: {to_email} | Subject: {subject}")
        return True

    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = SENDER_EMAIL
        msg["To"] = to_email

        msg.attach(MIMEText(html_body, "html"))

        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
            if SMTP_USER and SMTP_PASS:
                server.login(SMTP_USER, SMTP_PASS)
            server.send_message(msg)

        logger.info(f"Email sent to {to_email}: {subject}")
        return True
    except Exception as e:
        logger.error(f"Failed to send email to {to_email}: {e}")
        return False


def _build_listing_notification_html(listing: Listing) -> str:
    """Build HTML email body for a listing notification."""
    score = listing.lifestyle_score or 0
    price = int(listing.price) if listing.price else 0
    verdict = {
        "underpriced": "Ucuz 🟢",
        "fair": "Adil 🟡",
        "overpriced": "Pahalı 🔴",
    }.get(listing.price_verdict or "fair", "Adil")

    return f"""
    <html>
    <head>
        <meta charset="UTF-8">
        <style>
            body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; color: #333; }}
            .container {{ max-width: 600px; margin: 0 auto; padding: 20px; background: #f9fafb; }}
            .card {{ background: white; border-radius: 12px; padding: 24px; margin: 16px 0; border: 1px solid #e5e7eb; }}
            .title {{ font-size: 20px; font-weight: 700; margin: 0 0 8px 0; color: #1f2937; }}
            .subtitle {{ color: #6b7280; font-size: 14px; margin: 0 0 16px 0; }}
            .row {{ display: flex; gap: 16px; margin: 12px 0; }}
            .col {{ flex: 1; }}
            .label {{ color: #9ca3af; font-size: 13px; font-weight: 600; }}
            .value {{ color: #1f2937; font-size: 16px; font-weight: 600; margin-top: 4px; }}
            .lifestyle-badge {{
                display: inline-block;
                background: linear-gradient(135deg, #3b82f6, #0ea5e9);
                color: white;
                padding: 8px 12px;
                border-radius: 6px;
                font-weight: 700;
            }}
            .button {{
                display: inline-block;
                background: linear-gradient(135deg, #3b82f6, #0ea5e9);
                color: white;
                padding: 12px 24px;
                border-radius: 8px;
                text-decoration: none;
                font-weight: 600;
                margin: 16px 0;
            }}
            .footer {{ color: #9ca3af; font-size: 12px; text-align: center; margin-top: 24px; }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="card">
                <div class="title">🏡 Yeni Yüksek Kaliteli İlan</div>
                <div class="subtitle">Yaşam puanı 8+ olan bir ev, istediğin kriterlere uyuyor!</div>

                <div class="card">
                    <h2 class="title">{listing.title}</h2>
                    <div class="subtitle">{listing.district}, {listing.city}</div>

                    <div class="row">
                        <div class="col">
                            <div class="label">Fiyat</div>
                            <div class="value">₺{price:,}</div>
                        </div>
                        <div class="col">
                            <div class="label">Alan</div>
                            <div class="value">{listing.area_m2:.0f} m²</div>
                        </div>
                        <div class="col">
                            <div class="label">Oda</div>
                            <div class="value">{listing.room_count_total}</div>
                        </div>
                    </div>

                    <div class="row">
                        <div class="col">
                            <div class="label">Yaşam Kalitesi</div>
                            <div class="value"><span class="lifestyle-badge">{score:.1f} / 10</span></div>
                        </div>
                        <div class="col">
                            <div class="label">Fiyat Değerlendirmesi</div>
                            <div class="value">{verdict}</div>
                        </div>
                    </div>
                </div>

                <a href="http://127.0.0.1:8000/analyze?listing_id={listing.id}" class="button">
                    📊 Detaylı Analiz Yap
                </a>

                <div class="footer">
                    EmlakAI - Akıllı Emlak Platformu<br>
                    Bu bildirimi kapatmak için <a href="#">aboneliğinizi iptal edin</a>
                </div>
            </div>
        </div>
    </body>
    </html>
    """


def notify_high_lifestyle_listing(db: Session, listing: Listing) -> int:
    """Send listing notification to all subscribed users with matching preferences."""
    if not listing.lifestyle_score or listing.lifestyle_score < 8:
        return 0

    subscribers = (
        db.query(UserEmailPreference)
        .filter(
            UserEmailPreference.subscribed.is_(True),
            UserEmailPreference.min_lifestyle_score <= listing.lifestyle_score,
        )
        .all()
    )

    # Filter by room count preference
    if listing.room_count_total:
        subscribers = [
            s for s in subscribers
            if s.min_room_count is None or s.min_room_count == listing.room_count_total
        ]

    if not subscribers:
        return 0

    html_body = _build_listing_notification_html(listing)
    subject = f"🏡 {listing.title} — Yaşam Puanı {listing.lifestyle_score:.1f}/10"

    sent_count = 0
    for sub in subscribers:
        already_notified = (
            db.query(ListingNotificationSent)
            .filter(
                ListingNotificationSent.listing_id == listing.id,
                ListingNotificationSent.user_email == sub.email,
            )
            .first()
        )

        if already_notified:
            continue

        if send_email(sub.email, subject, html_body):
            notification = ListingNotificationSent(
                listing_id=listing.id,
                user_email=sub.email,
            )
            db.add(notification)
            sent_count += 1

    if sent_count > 0:
        db.commit()

    return sent_count


def subscribe_email(db: Session, email: str, user_id: int, min_lifestyle: int = 8, min_room_count: int | None = None) -> bool:
    """Subscribe a user to high-lifestyle listing notifications."""
    try:
        existing = db.query(UserEmailPreference).filter(UserEmailPreference.email == email).first()
        if existing:
            existing.subscribed = True
            existing.min_lifestyle_score = min_lifestyle
            existing.min_room_count = min_room_count
            db.commit()
            return True

        pref = UserEmailPreference(email=email, user_id=user_id, min_lifestyle_score=min_lifestyle, min_room_count=min_room_count)
        db.add(pref)
        db.commit()
        return True
    except Exception as e:
        logger.error(f"Failed to subscribe {email}: {e}")
        return False


def unsubscribe_email(db: Session, email: str) -> bool:
    """Unsubscribe a user from notifications."""
    try:
        pref = db.query(UserEmailPreference).filter(UserEmailPreference.email == email).first()
        if pref:
            pref.subscribed = False
            db.commit()
        return True
    except Exception as e:
        logger.error(f"Failed to unsubscribe {email}: {e}")
        return False


def get_subscription_status(db: Session, email: str) -> Optional[dict]:
    """Get subscription status for an email."""
    pref = db.query(UserEmailPreference).filter(UserEmailPreference.email == email).first()
    if not pref:
        return None
    return {
        "email": pref.email,
        "subscribed": pref.subscribed,
        "min_lifestyle_score": pref.min_lifestyle_score,
        "min_room_count": pref.min_room_count,
        "created_at": pref.created_at,
    }
