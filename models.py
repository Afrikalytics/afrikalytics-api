import json

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    update,
)
from sqlalchemy.orm import backref, relationship
from sqlalchemy.sql import func, text

from database import Base


# ================================================================
# MODEL: VerificationCode (2FA)
# ================================================================

class VerificationCode(Base):
    __tablename__ = "verification_codes"
    __table_args__ = (
        Index('ix_verification_code_lookup', 'user_id', 'code', 'is_used'),
    )

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    code = Column(String(6), nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    is_used = Column(Boolean, default=False, server_default=text("false"))
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    def __repr__(self):
        return f"<VerificationCode user_id={self.user_id}>"


# ================================================================
# MODEL: User
# ================================================================

class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint(
            "plan IN ('basic', 'professionnel', 'entreprise')",
            name="ck_users_plan",
        ),
        CheckConstraint(
            "admin_role IN ('super_admin', 'admin_content', 'admin_studies', 'admin_insights', 'admin_reports') OR admin_role IS NULL",
            name="ck_users_admin_role",
        ),
    )

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(255), unique=True, index=True, nullable=False)
    full_name = Column(String(255), nullable=False)
    hashed_password = Column(String(255), nullable=False)
    plan = Column(String(50), default="basic", index=True)  # basic, professionnel, entreprise
    order_id = Column(String(100), nullable=True)
    is_active = Column(Boolean, default=True, index=True)
    is_admin = Column(Boolean, default=False)
    admin_role = Column(String(50), nullable=True)  # super_admin, admin_content, admin_studies, admin_insights, admin_reports
    parent_user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)  # Pour les sous-utilisateurs entreprise
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), server_default=func.now())

    # Relationships
    subscriptions = relationship(
        "Subscription", backref="user", cascade="all, delete-orphan",
        foreign_keys="[Subscription.user_id]",
    )
    children = relationship(
        "User",
        backref=backref("parent", remote_side="User.id"),
        foreign_keys="[User.parent_user_id]",
    )

    def __repr__(self):
        return f"<User {self.email}>"


# ================================================================
# MODEL: Study
# ================================================================

class Study(Base):
    __tablename__ = "studies"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    category = Column(String(100), nullable=True)
    duration = Column(String(50), nullable=True)  # Ex: "15-20 min"
    deadline = Column(String(100), nullable=True)  # Ex: "28 Février 2024"
    status = Column(String(50), default="Ouvert", index=True)  # Ouvert, Fermé, Bientôt
    icon = Column(String(50), default="users")  # users, trending, chart, file
    embed_url_particulier = Column(String(500), nullable=True)  # URL iframe sondage particulier
    embed_url_entreprise = Column(String(500), nullable=True)  # URL iframe sondage entreprise
    embed_url_results = Column(String(500), nullable=True)  # URL iframe résultats (dashboard)
    report_url_basic = Column(String(500), nullable=True)
    report_url_premium = Column(String(500), nullable=True)
    is_active = Column(Boolean, default=True, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), server_default=func.now())

    # Relationships
    insights = relationship("Insight", backref="study", cascade="all, delete-orphan")
    reports = relationship("Report", backref="study", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Study {self.title}>"


# ================================================================
# MODEL: Subscription
# ================================================================

class Subscription(Base):
    __tablename__ = "subscriptions"
    __table_args__ = (
        CheckConstraint(
            "status IN ('active', 'cancelled', 'expired')",
            name="ck_subscriptions_status",
        ),
    )

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    plan = Column(String(50), nullable=False)
    status = Column(String(50), default="active", index=True)  # active, cancelled, expired
    woocommerce_order_id = Column(String(100), nullable=True)
    start_date = Column(DateTime(timezone=True), server_default=func.now())
    end_date = Column(DateTime(timezone=True), nullable=True, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    def __repr__(self):
        return f"<Subscription {self.user_id} - {self.plan}>"


# ================================================================
# MODEL: BlogPost
# ================================================================

class BlogPost(Base):
    __tablename__ = "blog_posts"

    # ID
    id = Column(Integer, primary_key=True, index=True)

    # Main content
    title = Column(String(255), nullable=False)
    slug = Column(String(255), unique=True, nullable=False, index=True)
    excerpt = Column(Text, nullable=True)
    content = Column(Text, nullable=False)
    featured_image = Column(String(500), nullable=True)

    # Organization
    category = Column(String(100), nullable=True, index=True)
    tags = Column(Text, nullable=True)  # JSON string: '["AI", "Tendances"]'

    # Author (relation to User)
    author_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    author = relationship("User", backref="blog_posts")

    # Status & Publication
    status = Column(String(50), default="draft", index=True)  # draft, published, scheduled
    published_at = Column(DateTime(timezone=True), nullable=True, index=True)
    scheduled_at = Column(DateTime(timezone=True), nullable=True)

    # SEO
    meta_title = Column(String(255), nullable=True)
    meta_description = Column(String(500), nullable=True)
    og_image = Column(String(500), nullable=True)  # Open Graph image

    # Analytics
    views = Column(Integer, default=0)

    # Reading time (calculated automatically)
    reading_time = Column(Integer, nullable=True)  # in minutes

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), server_default=func.now())

    def __repr__(self):
        return f"<BlogPost {self.title}>"

    # Helper methods
    def get_tags_list(self):
        """Convert JSON string to Python list"""
        if self.tags:
            try:
                return json.loads(self.tags)
            except Exception:
                return []
        return []

    def set_tags_list(self, tags_list):
        """Convert Python list to JSON string"""
        if tags_list:
            self.tags = json.dumps(tags_list)
        else:
            self.tags = None

    def is_published(self):
        """Check if the post is published"""
        return self.status == "published" and self.published_at is not None

    @classmethod
    def increment_views(cls, db, post_id: int):
        """Atomically increment view count to avoid race conditions."""
        db.query(cls).filter(cls.id == post_id).update(
            {cls.views: cls.views + 1}, synchronize_session=False
        )
        db.commit()


# ================================================================
# MODEL: NewsletterSubscriber
# ================================================================

class NewsletterSubscriber(Base):
    __tablename__ = "newsletter_subscribers"

    # ID
    id = Column(Integer, primary_key=True, index=True)

    # Email
    email = Column(String(255), unique=True, nullable=False, index=True)

    # Status
    status = Column(String(50), default="active", index=True)  # active, unsubscribed

    # Confirmation (double opt-in)
    is_confirmed = Column(Boolean, default=False)
    confirmation_token = Column(String(255), nullable=True, index=True)
    confirmed_at = Column(DateTime(timezone=True), nullable=True)

    # Source
    source = Column(String(100), default="blog_footer")

    # Unsubscribe
    unsubscribe_token = Column(String(255), unique=True, nullable=True, index=True)
    unsubscribed_at = Column(DateTime(timezone=True), nullable=True)

    # Timestamps
    subscribed_at = Column(DateTime(timezone=True), server_default=func.now())
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    def __repr__(self):
        return f"<NewsletterSubscriber {self.email}>"

    def is_active_subscriber(self):
        """Check if the subscriber is active"""
        return self.status == "active" and self.is_confirmed


# ================================================================
# MODEL: NewsletterCampaign
# ================================================================

class NewsletterCampaign(Base):
    __tablename__ = "newsletter_campaigns"

    # ID
    id = Column(Integer, primary_key=True, index=True)

    # Associated blog post
    blog_post_id = Column(Integer, ForeignKey("blog_posts.id", ondelete="SET NULL"), nullable=True)
    blog_post = relationship("BlogPost", backref="newsletter_campaigns")

    # Email content
    subject = Column(String(255), nullable=False)
    preview_text = Column(String(255), nullable=True)

    # Status
    status = Column(String(50), default="draft")  # draft, scheduled, sent, failed

    # Sending
    sent_at = Column(DateTime(timezone=True), nullable=True)
    scheduled_at = Column(DateTime(timezone=True), nullable=True)

    # Stats
    recipients_count = Column(Integer, default=0)
    opened_count = Column(Integer, default=0)
    clicked_count = Column(Integer, default=0)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    def __repr__(self):
        return f"<NewsletterCampaign {self.subject}>"

    def get_open_rate(self):
        """Calculate open rate"""
        if self.recipients_count > 0:
            return round((self.opened_count / self.recipients_count) * 100, 2)
        return 0

    def get_click_rate(self):
        """Calculate click rate"""
        if self.recipients_count > 0:
            return round((self.clicked_count / self.recipients_count) * 100, 2)
        return 0


# ================================================================
# MODEL: Insight
# ================================================================

class Insight(Base):
    __tablename__ = "insights"

    id = Column(Integer, primary_key=True, index=True)
    study_id = Column(Integer, ForeignKey("studies.id", ondelete="CASCADE"), nullable=False, index=True)
    title = Column(String(255), nullable=False)
    summary = Column(Text, nullable=False)
    key_findings = Column(Text, nullable=True)
    recommendations = Column(Text, nullable=True)
    author = Column(String(255), nullable=True)  # TODO: should be FK to users.id
    images = Column(Text, nullable=True)  # JSON string: '["url1", "url2"]'
    is_published = Column(Boolean, default=False, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), server_default=func.now())

    def __repr__(self):
        return f"<Insight {self.title}>"


# ================================================================
# MODEL: Report
# ================================================================

class Report(Base):
    __tablename__ = "reports"
    __table_args__ = (
        CheckConstraint(
            "report_type IN ('basic', 'premium')",
            name="ck_reports_report_type",
        ),
    )

    id = Column(Integer, primary_key=True, index=True)
    study_id = Column(Integer, ForeignKey("studies.id", ondelete="CASCADE"), nullable=False, index=True)
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    file_url = Column(String(500), nullable=False)
    file_name = Column(String(255), nullable=True)
    # TODO: Breaking change — was String(50). Existing data must be migrated (Alembic).
    # Stores file size in bytes.
    file_size = Column(BigInteger, nullable=True)
    report_type = Column(String(50), nullable=True, index=True)  # basic, premium
    download_count = Column(Integer, default=0, server_default=text("0"))
    is_available = Column(Boolean, default=False, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), server_default=func.now())

    def __repr__(self):
        return f"<Report {self.title}>"


# ================================================================
# MODEL: Contact
# ================================================================

class Contact(Base):
    __tablename__ = "contacts"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False)
    email = Column(String(255), nullable=False)
    company = Column(String(255), nullable=True)
    message = Column(Text, nullable=False)
    is_read = Column(Boolean, default=False, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    def __repr__(self):
        return f"<Contact {self.name}>"


# ================================================================
# MODEL: AuditLog
# ================================================================

class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    action = Column(String(50), nullable=False)  # create, update, delete, login, logout, toggle_active, publish
    resource_type = Column(String(50), nullable=False)  # user, study, insight, report, blog_post
    resource_id = Column(Integer, nullable=True)
    details = Column(Text, nullable=True)  # JSON string with extra details
    ip_address = Column(String(45), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    user = relationship("User", backref="audit_logs")

    def __repr__(self):
        return f"<AuditLog {self.action} {self.resource_type} by user_id={self.user_id}>"


# ================================================================
# MODEL: TokenBlacklist (revoked JWT tokens)
# ================================================================

class TokenBlacklist(Base):
    __tablename__ = "token_blacklist"

    id = Column(Integer, primary_key=True, index=True)
    jti = Column(String(36), unique=True, nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    expires_at = Column(DateTime, nullable=False)
    created_at = Column(DateTime, default=func.now())
