"""backfill listing metadata

Revision ID: 20260330_0005
Revises: 20260330_0004
Create Date: 2026-03-30 00:45:00
"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "20260330_0005"
down_revision: Union[str, None] = "20260330_0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Eski seed kayitlarin medya ve tarih alanlarini da doldurup yeni API seklini zenginlestiririz.
    op.execute(
        """
        UPDATE listings
        SET image_count = 3,
            images = json_build_array(
                CONCAT('https://example.com/images/seed/', source_listing_id, '/1.jpg'),
                CONCAT('https://example.com/images/seed/', source_listing_id, '/2.jpg'),
                CONCAT('https://example.com/images/seed/', source_listing_id, '/3.jpg')
            ),
            published_at = TIMESTAMP WITH TIME ZONE '2026-03-01 09:00:00+00' + ((source_listing_id)::int * interval '1 day'),
            source_updated_at = TIMESTAMP WITH TIME ZONE '2026-03-01 09:00:00+00' + ((source_listing_id)::int * interval '1 day'),
            is_active = true
        WHERE source = 'seed'
          AND source_listing_id ~ '^[0-9]+$'
        """
    )


def downgrade() -> None:
    # Geri alinirsa backfill ile eklenen medya ve tarih bilgileri temizlenir.
    op.execute(
        """
        UPDATE listings
        SET image_count = 0,
            images = '[]'::json,
            published_at = NULL,
            source_updated_at = NULL
        WHERE source = 'seed'
          AND source_listing_id ~ '^[0-9]+$'
        """
    )
