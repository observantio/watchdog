"""
All SQLAlchemy models for the application, defining the database schema for tenants, users, groups, permissions, alert rules, incidents, notification channels, and audit logs. This module uses SQLAlchemy's declarative base to define models with relationships and constraints that enforce data integrity and support the application's multi-tenant architecture. Each model includes fields for tracking creation and update timestamps, as well as relationships to other models to facilitate access control and data retrieval based on user permissions. The module also defines association tables for many-to-many relationships between users, groups, permissions, alert rules, and notification channels.

Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
"""

from __future__ import annotations
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from sqlalchemy import (
    Column, String, Boolean, DateTime, ForeignKey, Table, Text, JSON, Index, Integer, UniqueConstraint, event, text
)
from sqlalchemy.orm import relationship, DeclarativeBase, Mapped, mapped_column
import uuid

from config import config


class Base(DeclarativeBase):
    pass

USERS_ID = 'users.id'
GROUPS_ID = 'groups.id'
TENANTS_ID = 'tenants.id'
CASCADE_ALL_DELETE_ORPHAN = 'all, delete-orphan'
ONDELETE_SET_NULL = 'SET NULL'

def generate_uuid():
    return str(uuid.uuid4())


user_groups = Table(
    'user_groups',
    Base.metadata,
    Column('user_id', String, ForeignKey(USERS_ID, ondelete='CASCADE'), primary_key=True),
    Column('group_id', String, ForeignKey(GROUPS_ID, ondelete='CASCADE'), primary_key=True),
    Index('idx_user_groups_user', 'user_id'),
    Index('idx_user_groups_group', 'group_id')
)

group_permissions = Table(
    'group_permissions',
    Base.metadata,
    Column('group_id', String, ForeignKey(GROUPS_ID, ondelete='CASCADE'), primary_key=True),
    Column('permission_id', String, ForeignKey('permissions.id', ondelete='CASCADE'), primary_key=True),
    Index('idx_group_permissions_group', 'group_id'),
    Index('idx_group_permissions_permission', 'permission_id')
)

user_permissions = Table(
    'user_permissions',
    Base.metadata,
    Column('user_id', String, ForeignKey(USERS_ID, ondelete='CASCADE'), primary_key=True),
    Column('permission_id', String, ForeignKey('permissions.id', ondelete='CASCADE'), primary_key=True),
    Index('idx_user_permissions_user', 'user_id'),
    Index('idx_user_permissions_permission', 'permission_id')
)

channel_groups = Table(
    'channel_groups',
    Base.metadata,
    Column('channel_id', String, ForeignKey('notification_channels.id', ondelete='CASCADE'), primary_key=True),
    Column('group_id', String, ForeignKey(GROUPS_ID, ondelete='CASCADE'), primary_key=True),
    Index('idx_channel_groups_channel', 'channel_id'),
    Index('idx_channel_groups_group', 'group_id')
)

rule_groups = Table(
    'rule_groups',
    Base.metadata,
    Column('rule_id', String, ForeignKey('alert_rules.id', ondelete='CASCADE'), primary_key=True),
    Column('group_id', String, ForeignKey(GROUPS_ID, ondelete='CASCADE'), primary_key=True),
    Index('idx_rule_groups_rule', 'rule_id'),
    Index('idx_rule_groups_group', 'group_id')
)


class Tenant(Base):
    """Tenant model for multi-tenancy."""
    __tablename__ = 'tenants'

    id: Mapped[str] = mapped_column(String, primary_key=True, default=generate_uuid)
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)
    display_name: Mapped[Optional[str]] = mapped_column(String(200))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    settings: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)
    users: Mapped[List["User"]] = relationship('User', back_populates='tenant', cascade=CASCADE_ALL_DELETE_ORPHAN)
    groups: Mapped[List["Group"]] = relationship('Group', back_populates='tenant', cascade=CASCADE_ALL_DELETE_ORPHAN)
    alert_rules: Mapped[List["AlertRule"]] = relationship('AlertRule', back_populates='tenant', cascade=CASCADE_ALL_DELETE_ORPHAN)
    alert_incidents: Mapped[List["AlertIncident"]] = relationship('AlertIncident', back_populates='tenant', cascade=CASCADE_ALL_DELETE_ORPHAN)
    notification_channels: Mapped[List["NotificationChannel"]] = relationship('NotificationChannel', back_populates='tenant', cascade=CASCADE_ALL_DELETE_ORPHAN)

    __table_args__ = (
        Index('idx_tenants_active', 'is_active'),
    )


class User(Base):
    """User model with enhanced security."""
    __tablename__ = 'users'

    id: Mapped[str] = mapped_column(String, primary_key=True, default=generate_uuid)
    tenant_id: Mapped[str] = mapped_column(String, ForeignKey(TENANTS_ID, ondelete='CASCADE'), nullable=False, index=True)
    username: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[Optional[str]] = mapped_column(String(200))
    org_id: Mapped[str] = mapped_column(String(100), nullable=False, default=config.DEFAULT_ORG_ID, index=True)
    role: Mapped[str] = mapped_column(String(20), nullable=False, default='user', index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_superuser: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    needs_password_change: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # MFA / TOTP fields
    mfa_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    must_setup_mfa: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    totp_secret: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    mfa_recovery_hashes: Mapped[Optional[List[str]]] = mapped_column(JSON, nullable=True)

    grafana_user_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, index=True)
    auth_provider: Mapped[str] = mapped_column(String(50), nullable=False, default="local", index=True)
    external_subject: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, unique=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)
    last_login: Mapped[Optional[datetime]] = mapped_column(DateTime)

    tenant: Mapped["Tenant"] = relationship('Tenant', back_populates='users')
    groups: Mapped[List["Group"]] = relationship('Group', secondary=user_groups, back_populates='members')
    permissions: Mapped[List["Permission"]] = relationship('Permission', secondary=user_permissions, back_populates='users')
    api_keys: Mapped[List["UserApiKey"]] = relationship('UserApiKey', back_populates='user', cascade=CASCADE_ALL_DELETE_ORPHAN)
    shared_api_key_links: Mapped[List["ApiKeyShare"]] = relationship('ApiKeyShare', foreign_keys='ApiKeyShare.shared_user_id', back_populates='shared_user', cascade=CASCADE_ALL_DELETE_ORPHAN)
    created_rules: Mapped[List["AlertRule"]] = relationship('AlertRule', foreign_keys='AlertRule.created_by', back_populates='creator')
    created_channels: Mapped[List["NotificationChannel"]] = relationship('NotificationChannel', foreign_keys='NotificationChannel.created_by', back_populates='creator')

    __table_args__ = (
        Index('idx_users_tenant_active', 'tenant_id', 'is_active'),
        Index('idx_users_role', 'role'),
        Index('idx_users_mfa_enabled', 'mfa_enabled'),
    )


class Group(Base):
    """Group model for team-based access control."""
    __tablename__ = 'groups'

    id: Mapped[str] = mapped_column(String, primary_key=True, default=generate_uuid)
    tenant_id: Mapped[str] = mapped_column(String, ForeignKey(TENANTS_ID, ondelete='CASCADE'), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    description: Mapped[Optional[str]] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    grafana_team_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)


    tenant: Mapped["Tenant"] = relationship('Tenant', back_populates='groups')
    members: Mapped[List["User"]] = relationship('User', secondary=user_groups, back_populates='groups')
    permissions: Mapped[List["Permission"]] = relationship('Permission', secondary=group_permissions, back_populates='groups')
    shared_channels: Mapped[List["NotificationChannel"]] = relationship('NotificationChannel', secondary=channel_groups, back_populates='shared_groups')
    shared_rules: Mapped[List["AlertRule"]] = relationship('AlertRule', secondary=rule_groups, back_populates='shared_groups')

    __table_args__ = (
        Index('idx_groups_tenant_active', 'tenant_id', 'is_active'),
        Index('idx_groups_tenant_name', 'tenant_id', 'name', unique=True),
    )


class UserApiKey(Base):
    """API keys for observability tenants."""
    __tablename__ = 'user_api_keys'

    id: Mapped[str] = mapped_column(String, primary_key=True, default=generate_uuid)
    tenant_id: Mapped[str] = mapped_column(String, ForeignKey(TENANTS_ID, ondelete='CASCADE'), nullable=False, index=True)
    user_id: Mapped[str] = mapped_column(String, ForeignKey(USERS_ID, ondelete='CASCADE'), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    key: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    otlp_token: Mapped[Optional[str]] = mapped_column(String(200), nullable=True, unique=True, index=True)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)

    user: Mapped["User"] = relationship('User', back_populates='api_keys')
    shares: Mapped[List["ApiKeyShare"]] = relationship('ApiKeyShare', back_populates='api_key', cascade=CASCADE_ALL_DELETE_ORPHAN)

    __table_args__ = (
        Index('idx_user_api_keys_user', 'user_id'),
        Index('idx_user_api_keys_tenant', 'tenant_id'),
        Index('idx_user_api_keys_enabled', 'is_enabled'),
        Index('idx_user_api_keys_otlp_token', 'otlp_token'),
    )


class ApiKeyShare(Base):
    """Share grants for API keys (view + use only)."""
    __tablename__ = 'api_key_shares'

    id: Mapped[str] = mapped_column(String, primary_key=True, default=generate_uuid)
    tenant_id: Mapped[str] = mapped_column(String, ForeignKey(TENANTS_ID, ondelete='CASCADE'), nullable=False, index=True)
    api_key_id: Mapped[str] = mapped_column(String, ForeignKey('user_api_keys.id', ondelete='CASCADE'), nullable=False, index=True)
    owner_user_id: Mapped[str] = mapped_column(String, ForeignKey(USERS_ID, ondelete='CASCADE'), nullable=False, index=True)
    shared_user_id: Mapped[str] = mapped_column(String, ForeignKey(USERS_ID, ondelete='CASCADE'), nullable=False, index=True)
    can_use: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    api_key: Mapped["UserApiKey"] = relationship('UserApiKey', back_populates='shares')
    shared_user: Mapped["User"] = relationship('User', foreign_keys=[shared_user_id], back_populates='shared_api_key_links')

    __table_args__ = (
        UniqueConstraint('api_key_id', 'shared_user_id', name='uq_api_key_shares_key_user'),
        Index('idx_api_key_shares_tenant', 'tenant_id'),
        Index('idx_api_key_shares_owner', 'owner_user_id'),
        Index('idx_api_key_shares_shared_user', 'shared_user_id'),
    )


class PurgedSilence(Base):
    """Records silences that were purged (hidden) by the application.

    AlertManager persists expired silences; to provide a UX where a
    deleted silence is no longer visible, we store purged IDs here and
    exclude them from API results.
    """
    __tablename__ = 'purged_silences'

    id: Mapped[str] = mapped_column(String, primary_key=True)
    tenant_id: Mapped[Optional[str]] = mapped_column(String, ForeignKey(TENANTS_ID, ondelete='CASCADE'), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    __table_args__ = (
        Index('idx_purged_silences_tenant', 'tenant_id'),
    )


class Permission(Base):
    """Permission model for fine-grained access control."""
    __tablename__ = 'permissions'

    id: Mapped[str] = mapped_column(String, primary_key=True, default=generate_uuid)
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)
    display_name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    resource_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    action: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    groups: Mapped[List["Group"]] = relationship('Group', secondary=group_permissions, back_populates='permissions')
    users: Mapped[List["User"]] = relationship('User', secondary=user_permissions, back_populates='permissions')

    __table_args__ = (
        Index('idx_permissions_resource_action', 'resource_type', 'action'),
    )


class AlertRule(Base):
    """Alert rule with tenant and group scoping."""
    __tablename__ = 'alert_rules'

    id: Mapped[str] = mapped_column(String, primary_key=True, default=generate_uuid)
    tenant_id: Mapped[str] = mapped_column(String, ForeignKey(TENANTS_ID, ondelete='CASCADE'), nullable=False, index=True)
    created_by: Mapped[Optional[str]] = mapped_column(String, ForeignKey(USERS_ID, ondelete=ONDELETE_SET_NULL))
    org_id: Mapped[Optional[str]] = mapped_column(String, nullable=True, index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    group: Mapped[str] = mapped_column(String(100), nullable=False, default=config.DEFAULT_RULE_GROUP)
    expr: Mapped[str] = mapped_column(Text, nullable=False)
    duration: Mapped[str] = mapped_column(String(20), nullable=False, default='5m')
    severity: Mapped[str] = mapped_column(String(20), nullable=False, default='warning', index=True)
    labels: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)
    annotations: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    notification_channels: Mapped[List[Any]] = mapped_column(JSON, default=list)
    visibility: Mapped[str] = mapped_column(String(20), nullable=False, default='private', index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)

    tenant: Mapped["Tenant"] = relationship('Tenant', back_populates='alert_rules')
    creator: Mapped[Optional["User"]] = relationship('User', foreign_keys=[created_by], back_populates='created_rules')
    shared_groups: Mapped[List["Group"]] = relationship('Group', secondary=rule_groups, back_populates='shared_rules')

    __table_args__ = (
        Index('idx_alert_rules_tenant_enabled', 'tenant_id', 'enabled'),
        Index('idx_alert_rules_severity', 'severity'),
        Index('idx_alert_rules_visibility', 'visibility'),
    )


class AlertIncident(Base):
    """Historical alert incidents with lightweight ticket metadata."""
    __tablename__ = 'alert_incidents'

    id: Mapped[str] = mapped_column(String, primary_key=True, default=generate_uuid)
    tenant_id: Mapped[str] = mapped_column(String, ForeignKey(TENANTS_ID, ondelete='CASCADE'), nullable=False, index=True)
    fingerprint: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    alert_name: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    severity: Mapped[str] = mapped_column(String(20), nullable=False, default='warning', index=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default='open', index=True)
    assignee: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    notes: Mapped[List[Any]] = mapped_column(JSON, default=list)
    labels: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)
    annotations: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)
    starts_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True, index=True)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc), index=True)
    resolved_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)

    tenant: Mapped["Tenant"] = relationship('Tenant', back_populates='alert_incidents')

    __table_args__ = (
        Index('idx_alert_incidents_tenant_status', 'tenant_id', 'status'),
        Index('idx_alert_incidents_tenant_fingerprint', 'tenant_id', 'fingerprint', unique=True),
    )


class NotificationChannel(Base):
    """Notification channel with tenant and group scoping."""
    __tablename__ = 'notification_channels'

    id: Mapped[str] = mapped_column(String, primary_key=True, default=generate_uuid)
    tenant_id: Mapped[str] = mapped_column(String, ForeignKey(TENANTS_ID, ondelete='CASCADE'), nullable=False, index=True)
    created_by: Mapped[Optional[str]] = mapped_column(String, ForeignKey('users.id', ondelete=ONDELETE_SET_NULL))
    name: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    config: Mapped[Dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    visibility: Mapped[str] = mapped_column(String(20), nullable=False, default='private', index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)

    tenant: Mapped["Tenant"] = relationship('Tenant', back_populates='notification_channels')
    creator: Mapped[Optional["User"]] = relationship('User', foreign_keys=[created_by], back_populates='created_channels')
    shared_groups: Mapped[List["Group"]] = relationship('Group', secondary=channel_groups, back_populates='shared_channels')

    __table_args__ = (
        Index('idx_notification_channels_tenant_enabled', 'tenant_id', 'enabled'),
        Index('idx_notification_channels_type', 'type'),
        Index('idx_notification_channels_visibility', 'visibility'),
    )


class AuditLog(Base):
    """Audit log for tracking all actions."""
    __tablename__ = 'audit_logs'

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[Optional[str]] = mapped_column(String, ForeignKey(TENANTS_ID, ondelete='CASCADE'), index=True)
    user_id: Mapped[Optional[str]] = mapped_column(String, ForeignKey(USERS_ID, ondelete=ONDELETE_SET_NULL), index=True)
    action: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    resource_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    resource_id: Mapped[Optional[str]] = mapped_column(String, index=True)
    details: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON)
    ip_address: Mapped[Optional[str]] = mapped_column(String(45))
    user_agent: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False, index=True)

    __table_args__ = (
        Index('idx_audit_logs_tenant_created', 'tenant_id', 'created_at'),
        Index('idx_audit_logs_user_created', 'user_id', 'created_at'),
        Index('idx_audit_logs_action', 'action'),
    )


# Ensure audit_logs are immutable at creation time for Postgres-backed schemas.
# This attaches DB-level DDL to `Base.metadata.create_all()` so fresh installs
# get the trigger/function without a separate migration step.
@event.listens_for(AuditLog.__table__, 'after_create')
def _create_audit_logs_immutable(target, connection, **kw):
    if connection.dialect.name != 'postgresql':
        return
    # create function (idempotent)
    connection.execute(text("""
        CREATE OR REPLACE FUNCTION prevent_audit_log_mutation()
        RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION 'audit_logs are immutable';
        END;
        $$ LANGUAGE plpgsql;
    """))
    # create trigger (safe if exists)
    connection.execute(text("""
        DROP TRIGGER IF EXISTS trg_audit_logs_immutable ON audit_logs;
        CREATE TRIGGER trg_audit_logs_immutable
        BEFORE UPDATE OR DELETE ON audit_logs
        FOR EACH ROW
        EXECUTE FUNCTION prevent_audit_log_mutation();
    """))


dashboard_groups = Table(
    'dashboard_groups',
    Base.metadata,
    Column('dashboard_id', String, ForeignKey('grafana_dashboards.id', ondelete='CASCADE'), primary_key=True),
    Column('group_id', String, ForeignKey(GROUPS_ID, ondelete='CASCADE'), primary_key=True),
    Index('idx_dashboard_groups_dashboard', 'dashboard_id'),
    Index('idx_dashboard_groups_group', 'group_id')
)

datasource_groups = Table(
    'datasource_groups',
    Base.metadata,
    Column('datasource_id', String, ForeignKey('grafana_datasources.id', ondelete='CASCADE'), primary_key=True),
    Column('group_id', String, ForeignKey(GROUPS_ID, ondelete='CASCADE'), primary_key=True),
    Index('idx_datasource_groups_datasource', 'datasource_id'),
    Index('idx_datasource_groups_group', 'group_id')
)


class GrafanaDashboard(Base):
    """Grafana dashboard ownership and permissions."""
    __tablename__ = 'grafana_dashboards'

    id: Mapped[str] = mapped_column(String, primary_key=True, default=generate_uuid)
    tenant_id: Mapped[str] = mapped_column(String, ForeignKey(TENANTS_ID, ondelete='CASCADE'), nullable=False, index=True)
    created_by: Mapped[Optional[str]] = mapped_column(String, ForeignKey(USERS_ID, ondelete=ONDELETE_SET_NULL))
    grafana_uid: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    grafana_id: Mapped[Optional[int]] = mapped_column(Integer)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    folder_uid: Mapped[Optional[str]] = mapped_column(String(100))
    visibility: Mapped[str] = mapped_column(String(20), nullable=False, default='private', index=True)
    tags: Mapped[List[Any]] = mapped_column(JSON, default=list)
    is_hidden: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)
    hidden_by: Mapped[List[Any]] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)


    tenant: Mapped["Tenant"] = relationship('Tenant')
    creator: Mapped[Optional["User"]] = relationship('User', foreign_keys=[created_by])
    shared_groups: Mapped[List["Group"]] = relationship('Group', secondary=dashboard_groups)

    __table_args__ = (
        Index('idx_grafana_dashboards_tenant', 'tenant_id'),
        Index('idx_grafana_dashboards_uid', 'grafana_uid', unique=True),
        Index('idx_grafana_dashboards_visibility', 'visibility'),
    )


class GrafanaDatasource(Base):
    """Grafana datasource ownership and permissions."""
    __tablename__ = 'grafana_datasources'

    id: Mapped[str] = mapped_column(String, primary_key=True, default=generate_uuid)
    tenant_id: Mapped[str] = mapped_column(String, ForeignKey(TENANTS_ID, ondelete='CASCADE'), nullable=False, index=True)
    created_by: Mapped[Optional[str]] = mapped_column(String, ForeignKey(USERS_ID, ondelete=ONDELETE_SET_NULL))
    grafana_uid: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    grafana_id: Mapped[Optional[int]] = mapped_column(Integer)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    type: Mapped[str] = mapped_column(String(100), nullable=False)
    visibility: Mapped[str] = mapped_column(String(20), nullable=False, default='private', index=True)
    is_hidden: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)
    hidden_by: Mapped[List[Any]] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)


    tenant: Mapped["Tenant"] = relationship('Tenant')
    creator: Mapped[Optional["User"]] = relationship('User', foreign_keys=[created_by])
    shared_groups: Mapped[List["Group"]] = relationship('Group', secondary=datasource_groups)

    __table_args__ = (
        Index('idx_grafana_datasources_tenant', 'tenant_id'),
        Index('idx_grafana_datasources_uid', 'grafana_uid', unique=True),
        Index('idx_grafana_datasources_visibility', 'visibility'),
    )

