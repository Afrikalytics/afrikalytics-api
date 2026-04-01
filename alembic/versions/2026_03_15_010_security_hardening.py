"""Phase 4 security hardening: hash API keys + newsletter tokens, upgrade AuditLog.

Revision ID: 010
Revises: 009
Create Date: 2026-03-15

Changes
-------

1. api_keys table — replace plaintext ``key`` column with:
   - ``key_hash``   VARCHAR(64) UNIQUE NOT NULL — SHA-256 hex digest
   - ``key_prefix`` VARCHAR(8)  NOT NULL        — first 8 chars for display

   Data migration: existing plaintext keys are hashed in place so that no
   existing key becomes permanently invalid after the migration.  The prefix
   is derived from the first 8 chars of the current plaintext value (which
   already starts with "ak_").

   NOTE: After applying this migration all callers that previously looked up
   keys with ``WHERE key = :value`` must be updated to hash the inbound value
   and query ``WHERE key_hash = :hash`` instead.  The application routers were
   updated in the same commit as this migration.

2. newsletter_subscribers table — replace plaintext token columns with hashes:
   - Remove: ``confirmation_token``  VARCHAR(255)
   - Remove: ``unsubscribe_token``   VARCHAR(255)
   - Add:    ``confirmation_token_hash``   VARCHAR(64) — SHA-256 of the raw token
   - Add:    ``confirmation_token_prefix`` VARCHAR(8)  — first 8 chars for logs
   - Add:    ``unsubscribe_token_hash``    VARCHAR(64) — SHA-256 of the raw token
   - Add:    ``unsubscribe_token_prefix``  VARCHAR(8)  — first 8 chars for logs

   Data migration: existing plaintext tokens are hashed in place so that
   existing confirmation/unsubscribe links (already emailed) continue to work.
   Token prefixes are derived from the first 8 chars of each plaintext value.

3. audit_logs table — add ``user_agent`` column and widen ``ip_address``:
   - Add:    ``user_agent``  VARCHAR(500) — browser/client identifier
   - Widen:  ``ip_address``  VARCHAR(45)  — was VARCHAR(50), aligned with IPv6 max
   - Widen:  ``action``      VARCHAR(100) — was VARCHAR(50), allows more descriptive actions
   - Add:    index on ``created_at`` for time-range queries and partition-based cleanup

Downgrade
---------
The downgrade path removes the new columns and restores the old ones with
NULL values — existing hashed data cannot be reversed to plaintext, so any
confirmation/unsubscribe links emailed before the downgrade will stop working.
This is an intentional and documented limitation.
"""
import hashlib
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import text

# revision identifiers
revision: str = "010"
down_revision: Union[str, None] = "009"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _sha256(value: str) -> str:
    """Return lowercase hex SHA-256 digest of a UTF-8 string."""
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Upgrade
# ---------------------------------------------------------------------------

def upgrade() -> None:
    conn = op.get_bind()

    # ------------------------------------------------------------------ #
    # 1.  api_keys — replace plaintext key with key_hash + key_prefix     #
    # ------------------------------------------------------------------ #

    # Step 1a: add the new columns (nullable initially for the data migration)
    op.add_column(
        "api_keys",
        sa.Column("key_hash", sa.String(64), nullable=True),
    )
    op.add_column(
        "api_keys",
        sa.Column("key_prefix", sa.String(8), nullable=True),
    )

    # Step 1b: populate the new columns from existing plaintext keys
    rows = conn.execute(text("SELECT id, key FROM api_keys")).fetchall()
    for row in rows:
        key_id = row[0]
        plaintext_key = row[1] or ""
        key_hash = _sha256(plaintext_key)
        key_prefix = plaintext_key[:8]
        conn.execute(
            text(
                "UPDATE api_keys SET key_hash = :hash, key_prefix = :prefix "
                "WHERE id = :id"
            ),
            {"hash": key_hash, "prefix": key_prefix, "id": key_id},
        )

    # Step 1c: enforce NOT NULL and add unique index on key_hash
    op.alter_column("api_keys", "key_hash", nullable=False)
    op.alter_column("api_keys", "key_prefix", nullable=False)

    op.create_index(
        "ix_api_keys_key_hash",
        "api_keys",
        ["key_hash"],
        unique=True,
    )

    # Step 1d: drop the old plaintext key column and its index
    op.drop_index("ix_api_keys_key", table_name="api_keys")  # if it exists
    op.drop_column("api_keys", "key")

    # ------------------------------------------------------------------ #
    # 2.  newsletter_subscribers — hash confirmation + unsubscribe tokens #
    # ------------------------------------------------------------------ #

    # Step 2a: add hashed + prefix columns (nullable for migration)
    op.add_column(
        "newsletter_subscribers",
        sa.Column("confirmation_token_hash", sa.String(64), nullable=True),
    )
    op.add_column(
        "newsletter_subscribers",
        sa.Column("confirmation_token_prefix", sa.String(8), nullable=True),
    )
    op.add_column(
        "newsletter_subscribers",
        sa.Column("unsubscribe_token_hash", sa.String(64), nullable=True),
    )
    op.add_column(
        "newsletter_subscribers",
        sa.Column("unsubscribe_token_prefix", sa.String(8), nullable=True),
    )

    # Step 2b: populate from existing plaintext tokens
    rows = conn.execute(
        text(
            "SELECT id, confirmation_token, unsubscribe_token "
            "FROM newsletter_subscribers"
        )
    ).fetchall()

    for row in rows:
        sub_id = row[0]
        conf_token = row[1] or ""
        unsub_token = row[2] or ""

        conf_hash = _sha256(conf_token) if conf_token else None
        conf_prefix = conf_token[:8] if conf_token else None
        unsub_hash = _sha256(unsub_token) if unsub_token else None
        unsub_prefix = unsub_token[:8] if unsub_token else None

        conn.execute(
            text(
                "UPDATE newsletter_subscribers SET "
                "confirmation_token_hash = :ch, "
                "confirmation_token_prefix = :cp, "
                "unsubscribe_token_hash = :uh, "
                "unsubscribe_token_prefix = :up "
                "WHERE id = :id"
            ),
            {
                "ch": conf_hash,
                "cp": conf_prefix,
                "uh": unsub_hash,
                "up": unsub_prefix,
                "id": sub_id,
            },
        )

    # Step 2c: create indexes on the hash columns for O(1) token lookup
    op.create_index(
        "ix_newsletter_subscribers_conf_token_hash",
        "newsletter_subscribers",
        ["confirmation_token_hash"],
    )
    op.create_index(
        "ix_newsletter_subscribers_unsub_token_hash",
        "newsletter_subscribers",
        ["unsubscribe_token_hash"],
    )

    # Step 2d: drop the old plaintext token columns
    op.drop_column("newsletter_subscribers", "confirmation_token")
    op.drop_column("newsletter_subscribers", "unsubscribe_token")

    # ------------------------------------------------------------------ #
    # 3.  audit_logs — add user_agent, widen columns, index created_at   #
    # ------------------------------------------------------------------ #

    # Add user_agent column
    op.add_column(
        "audit_logs",
        sa.Column("user_agent", sa.String(500), nullable=True),
    )

    # Widen action column: VARCHAR(50) -> VARCHAR(100)
    op.alter_column(
        "audit_logs",
        "action",
        existing_type=sa.String(50),
        type_=sa.String(100),
        existing_nullable=False,
    )

    # Widen ip_address column: VARCHAR(50) -> VARCHAR(45)
    # (45 chars covers the longest IPv6 representation)
    op.alter_column(
        "audit_logs",
        "ip_address",
        existing_type=sa.String(50),
        type_=sa.String(45),
        existing_nullable=True,
    )

    # Add index on created_at for time-range queries and cleanup jobs
    op.create_index(
        "ix_audit_logs_created_at",
        "audit_logs",
        ["created_at"],
    )


# ---------------------------------------------------------------------------
# Downgrade
# ---------------------------------------------------------------------------

def downgrade() -> None:
    conn = op.get_bind()

    # ------------------------------------------------------------------ #
    # 3.  Revert audit_logs changes                                        #
    # ------------------------------------------------------------------ #
    op.drop_index("ix_audit_logs_created_at", table_name="audit_logs")

    op.alter_column(
        "audit_logs",
        "ip_address",
        existing_type=sa.String(45),
        type_=sa.String(50),
        existing_nullable=True,
    )

    op.alter_column(
        "audit_logs",
        "action",
        existing_type=sa.String(100),
        type_=sa.String(50),
        existing_nullable=False,
    )

    op.drop_column("audit_logs", "user_agent")

    # ------------------------------------------------------------------ #
    # 2.  Revert newsletter_subscribers — restore plaintext columns (NULL) #
    # ------------------------------------------------------------------ #
    # NOTE: we restore the column but cannot recover plaintext from hashes.
    # Any confirmation/unsubscribe links sent after migration 010 will break.
    op.drop_index(
        "ix_newsletter_subscribers_unsub_token_hash",
        table_name="newsletter_subscribers",
    )
    op.drop_index(
        "ix_newsletter_subscribers_conf_token_hash",
        table_name="newsletter_subscribers",
    )

    op.add_column(
        "newsletter_subscribers",
        sa.Column("unsubscribe_token", sa.String(255), nullable=True),
    )
    op.add_column(
        "newsletter_subscribers",
        sa.Column("confirmation_token", sa.String(255), nullable=True),
    )

    op.drop_column("newsletter_subscribers", "unsubscribe_token_prefix")
    op.drop_column("newsletter_subscribers", "unsubscribe_token_hash")
    op.drop_column("newsletter_subscribers", "confirmation_token_prefix")
    op.drop_column("newsletter_subscribers", "confirmation_token_hash")

    # ------------------------------------------------------------------ #
    # 1.  Revert api_keys — restore plaintext key column (NULL)           #
    # ------------------------------------------------------------------ #
    # NOTE: we restore the column but cannot recover plaintext from hashes.
    op.drop_index("ix_api_keys_key_hash", table_name="api_keys")

    op.add_column(
        "api_keys",
        sa.Column("key", sa.String(64), nullable=True),
    )

    # Restore a unique index on the old key column
    op.create_index("ix_api_keys_key", "api_keys", ["key"], unique=True)

    op.drop_column("api_keys", "key_prefix")
    op.drop_column("api_keys", "key_hash")
