from __future__ import annotations

import enum
import uuid

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    BigInteger,
    LargeBinary,
    Text,
    JSON,
    String,
    Uuid,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import relationship

from app.db import Base


def _uuid_str() -> str:
    return str(uuid.uuid4())


class SourceKind(str, enum.Enum):
    rss = "rss"
    arxiv = "arxiv"
    github = "github"
    github_trending = "github_trending"
    hn = "hn"
    reddit = "reddit"
    sitemap = "sitemap"
    congress = "congress"
    twitter = "twitter"
    mastodon = "mastodon"
    bluesky = "bluesky"
    semantic_scholar = "semantic_scholar"
    hf_papers = "hf_papers"
    nvd = "nvd"
    custom = "custom"


class ScrapeDecision(str, enum.Enum):
    skip = "skip"
    fetch_full = "fetch_full"
    fetch_full_priority = "fetch_full_priority"
    fetch_watch = "fetch_watch"


class EventType(str, enum.Enum):
    MODEL_RELEASE = "MODEL_RELEASE"
    CHIP_HARDWARE = "CHIP_HARDWARE"
    BIG_TECH_ANNOUNCEMENT = "BIG_TECH_ANNOUNCEMENT"
    STARTUP_FUNDING = "STARTUP_FUNDING"
    M_AND_A = "M_AND_A"
    OPEN_SOURCE_RELEASE = "OPEN_SOURCE_RELEASE"
    RESEARCH_PAPER = "RESEARCH_PAPER"
    BENCHMARK_RESULT = "BENCHMARK_RESULT"
    SECURITY_INCIDENT = "SECURITY_INCIDENT"
    POLICY_REGULATION = "POLICY_REGULATION"
    GOVERNMENT_ACTION = "GOVERNMENT_ACTION"
    PRODUCT_LAUNCH = "PRODUCT_LAUNCH"
    OTHER = "OTHER"


class Source(Base):
    __tablename__ = "sources"

    id = Column(Uuid(as_uuid=False), primary_key=True, default=_uuid_str)
    name = Column(Text, nullable=False, unique=True)
    kind = Column(Text, nullable=False)
    base_url = Column(Text, nullable=True)
    feed_url = Column(Text, nullable=True)
    authority = Column(Float, nullable=False)
    always_scrape = Column(Boolean, nullable=False, default=False)
    priority_poll = Column(Boolean, nullable=False, default=False)
    enabled = Column(Boolean, nullable=False, default=True)
    rate_limit_rps = Column(Float, nullable=False, default=0.5)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    raw_items = relationship("RawItem", back_populates="source")


class RawItem(Base):
    __tablename__ = "raw_items"

    id = Column(Uuid(as_uuid=False), primary_key=True, default=_uuid_str)
    source_id = Column(Uuid(as_uuid=False), ForeignKey("sources.id"), nullable=False)
    external_id = Column(Text, nullable=False)
    url = Column(Text, nullable=False)
    title = Column(Text, nullable=False)
    snippet = Column(Text, nullable=True)
    author = Column(Text, nullable=True)
    published_at = Column(DateTime(timezone=True), nullable=True)
    fetched_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    language = Column(Text, nullable=False, default="en")

    social_hn_points = Column(Integer, nullable=True)
    social_hn_comments = Column(Integer, nullable=True)
    social_reddit_upvotes = Column(Integer, nullable=True)
    social_github_stars = Column(Integer, nullable=True)

    pre_score = Column(Float, nullable=True)
    scrape_decision = Column(Text, nullable=True)
    scrape_reason = Column(Text, nullable=True)

    canonical_hash = Column(Text, nullable=False)

    source = relationship("Source", back_populates="raw_items")
    article = relationship("Article", back_populates="raw_item", uselist=False)

    __table_args__ = (
        UniqueConstraint("source_id", "external_id", name="uq_raw_items_source_external"),
        UniqueConstraint("canonical_hash", name="uq_raw_items_canonical"),
        Index("ix_raw_items_fetched_at", "fetched_at"),
    )


class Article(Base):
    __tablename__ = "articles"

    id = Column(Uuid(as_uuid=False), primary_key=True, default=_uuid_str)
    raw_item_id = Column(Uuid(as_uuid=False), ForeignKey("raw_items.id"), unique=True)
    final_url = Column(Text, nullable=False)
    html = Column(Text, nullable=True)
    text = Column(Text, nullable=False)
    extraction_quality = Column(Float, nullable=False)
    embedding = Column(LargeBinary, nullable=False)

    content_type = Column(Text, nullable=False, default="news", server_default="news")

    event_type = Column(Text, nullable=False)
    topics = Column(JSON, nullable=False)
    entities = Column(JSON, nullable=False)
    funding_amount_usd = Column(BigInteger, nullable=True)
    global_score = Column(Float, nullable=False)
    urgent = Column(Boolean, nullable=False, default=False)
    summary = Column(Text, nullable=True)

    # Algorithm v2: importance scoring signals
    entity_prominence = Column(Float, nullable=True)
    social_velocity = Column(Float, nullable=True)
    cluster_velocity = Column(Float, nullable=True)
    event_rarity = Column(Float, nullable=True)
    independent_sources = Column(Integer, nullable=True)
    llm_score = Column(Float, nullable=True)
    llm_reasoning = Column(Text, nullable=True)
    final_score = Column(Float, nullable=True)

    # Algorithm v2: trust scoring
    trust_score = Column(Float, nullable=True)
    trust_label = Column(Text, nullable=True)
    trust_components = Column(JSON, nullable=True)
    hedging_ratio = Column(Float, nullable=True)
    attribution_ratio = Column(Float, nullable=True)
    specificity_score = Column(Float, nullable=True)
    has_primary_document = Column(Boolean, default=False, server_default="false")
    confirmation_level = Column(Text, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    raw_item = relationship("RawItem", back_populates="article")

    __table_args__ = (
        CheckConstraint("extraction_quality >= 0 and extraction_quality <= 1", name="ck_articles_quality"),
    )


class Cluster(Base):
    __tablename__ = "clusters"

    id = Column(Uuid(as_uuid=False), primary_key=True, default=_uuid_str)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    centroid_embedding = Column(LargeBinary, nullable=False)
    headline = Column(Text, nullable=False)
    top_article_id = Column(Uuid(as_uuid=False), ForeignKey("articles.id"), nullable=True)
    coverage_count = Column(Integer, nullable=False, default=0)
    sources_count = Column(Integer, nullable=False, default=0)
    max_global_score = Column(Float, nullable=False, default=0)
    first_seen_at = Column(DateTime(timezone=True), nullable=True)
    last_seen_at = Column(DateTime(timezone=True), nullable=True)

    # Algorithm v2: cluster-level scoring
    cluster_velocity = Column(Float, nullable=True)
    independent_sources_count = Column(Integer, nullable=True)
    has_official_confirmation = Column(Boolean, default=False, server_default="false")
    cluster_trust_score = Column(Float, nullable=True)
    cluster_trust_label = Column(Text, nullable=True)


class ClusterMember(Base):
    __tablename__ = "cluster_members"

    cluster_id = Column(Uuid(as_uuid=False), ForeignKey("clusters.id"), primary_key=True)
    article_id = Column(Uuid(as_uuid=False), ForeignKey("articles.id"), primary_key=True)
    similarity = Column(Float, nullable=False)

    __table_args__ = (
        UniqueConstraint("article_id", name="uq_cluster_members_article_id"),
        Index("ix_cluster_members_cluster", "cluster_id"),
    )


class User(Base):
    __tablename__ = "users"

    id = Column(Uuid(as_uuid=False), primary_key=True, default=_uuid_str)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    prefs = relationship("UserPref", back_populates="user", uselist=False)


class UserPref(Base):
    __tablename__ = "user_prefs"

    user_id = Column(Uuid(as_uuid=False), ForeignKey("users.id"), primary_key=True)
    min_show_score = Column(Float, nullable=False, default=55)
    min_urgent_score = Column(Float, nullable=False, default=85)
    serendipity = Column(Float, nullable=False, default=0.15)
    prefer_official_sources = Column(Boolean, nullable=False, default=False)
    prefer_research = Column(Float, nullable=False, default=1.0)
    prefer_startups = Column(Float, nullable=False, default=1.0)
    prefer_hardware = Column(Float, nullable=False, default=1.0)
    prefer_open_source = Column(Float, nullable=False, default=1.0)
    prefer_policy_safety = Column(Float, nullable=False, default=1.0)
    prefer_tutorials_tools = Column(Float, nullable=False, default=1.0)
    recency_bias = Column(Float, nullable=False, default=1.0)
    credibility_bias = Column(Float, nullable=False, default=1.0)
    hype_tolerance = Column(Float, nullable=False, default=1.0)

    user = relationship("User", back_populates="prefs")


class UserEntityWeight(Base):
    __tablename__ = "user_entity_weights"

    user_id = Column(Uuid(as_uuid=False), ForeignKey("users.id"), primary_key=True)
    entity = Column(Text, primary_key=True)
    weight = Column(Float, nullable=False, default=1.0)
    blocked = Column(Boolean, nullable=False, default=False)


class UserTopicWeight(Base):
    __tablename__ = "user_topic_weights"

    user_id = Column(Uuid(as_uuid=False), ForeignKey("users.id"), primary_key=True)
    topic = Column(Text, primary_key=True)
    weight = Column(Float, nullable=False, default=1.0)
    blocked = Column(Boolean, nullable=False, default=False)


class UserSourceWeight(Base):
    __tablename__ = "user_source_weights"

    user_id = Column(Uuid(as_uuid=False), ForeignKey("users.id"), primary_key=True)
    source_id = Column(Uuid(as_uuid=False), ForeignKey("sources.id"), primary_key=True)
    weight = Column(Float, nullable=False, default=1.0)
    blocked = Column(Boolean, nullable=False, default=False)


class EntityCanonMap(Base):
    __tablename__ = "entity_canon_maps"

    id = Column(Uuid(as_uuid=False), primary_key=True, default=_uuid_str)
    generated_at = Column(DateTime(timezone=True), server_default=func.now())
    canon_map = Column(JSON, nullable=False)
    cluster_count = Column(Integer, nullable=False)
    entity_count = Column(Integer, nullable=False)


class DailyDigest(Base):
    __tablename__ = "daily_digests"

    id = Column(Uuid(as_uuid=False), primary_key=True, default=_uuid_str)
    user_id = Column(Uuid(as_uuid=False), ForeignKey("users.id"), nullable=False)
    date = Column(DateTime(timezone=True), nullable=False)
    article_ids = Column(JSON, nullable=False)
    content_type = Column(Text, nullable=False, default="all", server_default="all")
    headline = Column(Text, nullable=True)
    executive_summary = Column(Text, nullable=True)
    llm_authored = Column(Boolean, nullable=False, default=False, server_default="false")
    storage_bucket = Column(Text, nullable=True)
    storage_path = Column(Text, nullable=True)
    longform_html = Column(Text, nullable=True)

    __table_args__ = (
        Index("ix_daily_digests_user_date_ct", "user_id", "date", "content_type", unique=True),
    )
