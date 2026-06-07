"""add location lookup tables and geospatial indexes

Revision ID: 20260402_0015
Revises: 20260401_0014
Create Date: 2026-04-02 10:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "20260402_0015"
down_revision: Union[str, Sequence[str], None] = "20260401_0014"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS postgis")
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    op.execute("CREATE EXTENSION IF NOT EXISTS unaccent")

    op.create_table(
        "locations",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("city_name", sa.String(length=100), nullable=False),
        sa.Column("district_name", sa.String(length=100), nullable=False),
        sa.Column("neighborhood_name", sa.String(length=100), nullable=False),
        sa.Column("city_canonical", sa.String(length=100), nullable=False),
        sa.Column("district_canonical", sa.String(length=100), nullable=False),
        sa.Column("neighborhood_canonical", sa.String(length=100), nullable=False),
        sa.Column("city_code", sa.String(length=16), nullable=True),
        sa.Column("district_code", sa.String(length=16), nullable=True),
        sa.Column("neighborhood_code", sa.String(length=16), nullable=True),
        sa.Column("centroid_latitude", sa.Float(), nullable=True),
        sa.Column("centroid_longitude", sa.Float(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "city_canonical",
            "district_canonical",
            "neighborhood_canonical",
            name="uq_locations_canonical_triplet",
        ),
    )

    op.create_index("ix_locations_city_canonical", "locations", ["city_canonical"], unique=False)
    op.create_index("ix_locations_district_canonical", "locations", ["district_canonical"], unique=False)
    op.create_index("ix_locations_neighborhood_canonical", "locations", ["neighborhood_canonical"], unique=False)
    op.create_index("ix_locations_city_code", "locations", ["city_code"], unique=False)
    op.create_index("ix_locations_district_code", "locations", ["district_code"], unique=False)
    op.create_index("ix_locations_neighborhood_code", "locations", ["neighborhood_code"], unique=False)

    op.create_table(
        "location_aliases",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("location_id", sa.Integer(), nullable=False),
        sa.Column("city_canonical", sa.String(length=100), nullable=False),
        sa.Column("district_canonical", sa.String(length=100), nullable=False),
        sa.Column("neighborhood_canonical", sa.String(length=100), nullable=False),
        sa.Column("alias_source", sa.String(length=50), nullable=True),
        sa.ForeignKeyConstraint(["location_id"], ["locations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "city_canonical",
            "district_canonical",
            "neighborhood_canonical",
            name="uq_location_aliases_canonical_triplet",
        ),
    )

    op.create_index("ix_location_aliases_location_id", "location_aliases", ["location_id"], unique=False)
    op.create_index("ix_location_aliases_city_canonical", "location_aliases", ["city_canonical"], unique=False)
    op.create_index("ix_location_aliases_district_canonical", "location_aliases", ["district_canonical"], unique=False)
    op.create_index(
        "ix_location_aliases_neighborhood_canonical",
        "location_aliases",
        ["neighborhood_canonical"],
        unique=False,
    )

    op.create_index(
        "ix_location_aliases_neighborhood_canonical_trgm",
        "location_aliases",
        ["neighborhood_canonical"],
        unique=False,
        postgresql_using="gin",
        postgresql_ops={"neighborhood_canonical": "gin_trgm_ops"},
    )

    op.add_column("listings", sa.Column("location_id", sa.Integer(), nullable=True))
    op.add_column("listings", sa.Column("city_code", sa.String(length=16), nullable=True))
    op.add_column("listings", sa.Column("district_code", sa.String(length=16), nullable=True))
    op.add_column("listings", sa.Column("neighborhood_code", sa.String(length=16), nullable=True))
    op.add_column("listings", sa.Column("location_match_confidence", sa.Float(), nullable=True))

    op.create_foreign_key(
        "fk_listings_location_id_locations",
        "listings",
        "locations",
        ["location_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_listings_location_id", "listings", ["location_id"], unique=False)
    op.create_index("ix_listings_city_code", "listings", ["city_code"], unique=False)
    op.create_index("ix_listings_district_code", "listings", ["district_code"], unique=False)
    op.create_index("ix_listings_neighborhood_code", "listings", ["neighborhood_code"], unique=False)

    op.execute(
        """
        INSERT INTO locations (
            city_name,
            district_name,
            neighborhood_name,
            city_canonical,
            district_canonical,
            neighborhood_canonical,
            centroid_latitude,
            centroid_longitude
        )
        SELECT
            MIN(city) AS city_name,
            MIN(district) AS district_name,
            MIN(neighborhood) AS neighborhood_name,
            city_canonical,
            district_canonical,
            neighborhood_canonical,
            AVG(latitude) AS centroid_latitude,
            AVG(longitude) AS centroid_longitude
        FROM listings
        WHERE city_canonical IS NOT NULL
          AND district_canonical IS NOT NULL
          AND neighborhood_canonical IS NOT NULL
        GROUP BY city_canonical, district_canonical, neighborhood_canonical
        ON CONFLICT ON CONSTRAINT uq_locations_canonical_triplet DO NOTHING
        """
    )

    op.execute(
        """
        INSERT INTO location_aliases (
            location_id,
            city_canonical,
            district_canonical,
            neighborhood_canonical,
            alias_source
        )
        SELECT
            l.id,
            l.city_canonical,
            l.district_canonical,
            l.neighborhood_canonical,
            'backfill'
        FROM locations l
        ON CONFLICT ON CONSTRAINT uq_location_aliases_canonical_triplet DO NOTHING
        """
    )

    op.execute(
        """
        UPDATE listings li
        SET
            location_id = loc.id,
            city_code = COALESCE(li.city_code, loc.city_code),
            district_code = COALESCE(li.district_code, loc.district_code),
            neighborhood_code = COALESCE(li.neighborhood_code, loc.neighborhood_code),
            location_match_confidence = COALESCE(li.location_match_confidence, 1.0)
        FROM locations loc
        WHERE li.city_canonical = loc.city_canonical
          AND li.district_canonical = loc.district_canonical
          AND li.neighborhood_canonical = loc.neighborhood_canonical
        """
    )

    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_listings_geo_point_gist
        ON listings
        USING gist ((ST_SetSRID(ST_MakePoint(longitude, latitude), 4326)::geography))
        WHERE longitude IS NOT NULL AND latitude IS NOT NULL
        """
    )



def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_listings_geo_point_gist")

    op.drop_index("ix_listings_neighborhood_code", table_name="listings")
    op.drop_index("ix_listings_district_code", table_name="listings")
    op.drop_index("ix_listings_city_code", table_name="listings")
    op.drop_index("ix_listings_location_id", table_name="listings")
    op.drop_constraint("fk_listings_location_id_locations", "listings", type_="foreignkey")

    op.drop_column("listings", "location_match_confidence")
    op.drop_column("listings", "neighborhood_code")
    op.drop_column("listings", "district_code")
    op.drop_column("listings", "city_code")
    op.drop_column("listings", "location_id")

    op.drop_index("ix_location_aliases_neighborhood_canonical_trgm", table_name="location_aliases")
    op.drop_index("ix_location_aliases_neighborhood_canonical", table_name="location_aliases")
    op.drop_index("ix_location_aliases_district_canonical", table_name="location_aliases")
    op.drop_index("ix_location_aliases_city_canonical", table_name="location_aliases")
    op.drop_index("ix_location_aliases_location_id", table_name="location_aliases")
    op.drop_table("location_aliases")

    op.drop_index("ix_locations_neighborhood_code", table_name="locations")
    op.drop_index("ix_locations_district_code", table_name="locations")
    op.drop_index("ix_locations_city_code", table_name="locations")
    op.drop_index("ix_locations_neighborhood_canonical", table_name="locations")
    op.drop_index("ix_locations_district_canonical", table_name="locations")
    op.drop_index("ix_locations_city_canonical", table_name="locations")
    op.drop_table("locations")
