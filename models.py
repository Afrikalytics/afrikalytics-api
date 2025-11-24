from sqlalchemy import Column, Integer, String, Boolean, DateTime, Text
from sqlalchemy.sql import func
from database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(255), unique=True, index=True, nullable=False)
    full_name = Column(String(255), nullable=False)
    hashed_password = Column(String(255), nullable=False)
    plan = Column(String(50), default="starter")  # starter, professional, enterprise
    order_id = Column(String(100), nullable=True)
    is_active = Column(Boolean, default=True)
    is_admin = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    def __repr__(self):
        return f"<User {self.email}>"


class Study(Base):
    __tablename__ = "studies"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    category = Column(String(100), nullable=True)
    duration = Column(String(50), nullable=True)  # Ex: "15-20 min"
    deadline = Column(String(100), nullable=True)  # Ex: "28 Février 2024"
    status = Column(String(50), default="Ouvert")  # Ouvert, Fermé, Bientôt
    icon = Column(String(50), default="users")  # users, trending, chart, file
    embed_url_particulier = Column(String(500), nullable=True)  # URL iframe sondage particulier
    embed_url_entreprise = Column(String(500), nullable=True)  # URL iframe sondage entreprise
    embed_url_results = Column(String(500), nullable=True)  # URL iframe résultats (dashboard)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    def __repr__(self):
        return f"<Study {self.title}>"


class Subscription(Base):
    __tablename__ = "subscriptions"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, index=True, nullable=False)
    plan = Column(String(50), nullable=False)
    status = Column(String(50), default="active")  # active, cancelled, expired
    woocommerce_order_id = Column(String(100), nullable=True)
    start_date = Column(DateTime(timezone=True), server_default=func.now())
    end_date = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    def __repr__(self):
        return f"<Subscription {self.user_id} - {self.plan}>"
