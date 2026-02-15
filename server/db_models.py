"""Database models for enterprise IAM system."""
from datetime import datetime, timezone
from sqlalchemy import (
    Column, String, Boolean, DateTime, ForeignKey, Table, Text, JSON, Index, Integer
)
from sqlalchemy.orm import relationship, declarative_base
import uuid

from config import config

Base = declarative_base()

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

    id = Column(String, primary_key=True, default=generate_uuid)
    name = Column(String(100), unique=True, nullable=False, index=True)
    display_name = Column(String(200))
    is_active = Column(Boolean, default=True, nullable=False)
    settings = Column(JSON, default=dict)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)
    users = relationship('User', back_populates='tenant', cascade=CASCADE_ALL_DELETE_ORPHAN)
    groups = relationship('Group', back_populates='tenant', cascade=CASCADE_ALL_DELETE_ORPHAN)
    alert_rules = relationship('AlertRule', back_populates='tenant', cascade=CASCADE_ALL_DELETE_ORPHAN)
    alert_incidents = relationship('AlertIncident', back_populates='tenant', cascade=CASCADE_ALL_DELETE_ORPHAN)
    notification_channels = relationship('NotificationChannel', back_populates='tenant', cascade=CASCADE_ALL_DELETE_ORPHAN)

    __table_args__ = (
        Index('idx_tenants_active', 'is_active'),
    )


class User(Base):
    """User model with enhanced security."""
    __tablename__ = 'users'

    id = Column(String, primary_key=True, default=generate_uuid)
    tenant_id = Column(String, ForeignKey(TENANTS_ID, ondelete='CASCADE'), nullable=False, index=True)
    username = Column(String(50), unique=True, nullable=False, index=True)
    email = Column(String(255), unique=True, nullable=False, index=True)
    hashed_password = Column(String(255), nullable=False)
    full_name = Column(String(200))
    org_id = Column(String(100), nullable=False, default=config.DEFAULT_ORG_ID, index=True)  
    role = Column(String(20), nullable=False, default='user', index=True)  
    is_active = Column(Boolean, default=True, nullable=False)
    is_superuser = Column(Boolean, default=False, nullable=False)
    needs_password_change = Column(Boolean, default=False, nullable=False)

    # MFA / TOTP fields
    mfa_enabled = Column(Boolean, default=False, nullable=False)
    must_setup_mfa = Column(Boolean, default=False, nullable=False)
    totp_secret = Column(Text, nullable=True)
    mfa_recovery_hashes = Column(JSON, nullable=True)

    grafana_user_id = Column(Integer, nullable=True, index=True)  
    auth_provider = Column(String(50), nullable=False, default="local", index=True)
    external_subject = Column(String(255), nullable=True, unique=True, index=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)
    last_login = Column(DateTime)

    tenant = relationship('Tenant', back_populates='users')
    groups = relationship('Group', secondary=user_groups, back_populates='members')
    permissions = relationship('Permission', secondary=user_permissions, back_populates='users')
    api_keys = relationship('UserApiKey', back_populates='user', cascade=CASCADE_ALL_DELETE_ORPHAN)
    created_rules = relationship('AlertRule', foreign_keys='AlertRule.created_by', back_populates='creator')
    created_channels = relationship('NotificationChannel', foreign_keys='NotificationChannel.created_by', back_populates='creator')

    __table_args__ = (
        Index('idx_users_tenant_active', 'tenant_id', 'is_active'),
        Index('idx_users_role', 'role'),
        Index('idx_users_mfa_enabled', 'mfa_enabled'),
    )


class Group(Base):
    """Group model for team-based access control."""
    __tablename__ = 'groups'

    id = Column(String, primary_key=True, default=generate_uuid)
    tenant_id = Column(String, ForeignKey(TENANTS_ID, ondelete='CASCADE'), nullable=False, index=True)
    name = Column(String(100), nullable=False, index=True)
    description = Column(Text)
    is_active = Column(Boolean, default=True, nullable=False)
    grafana_team_id = Column(Integer, nullable=True, index=True)  
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)


    tenant = relationship('Tenant', back_populates='groups')
    members = relationship('User', secondary=user_groups, back_populates='groups')
    permissions = relationship('Permission', secondary=group_permissions, back_populates='groups')
    shared_channels = relationship('NotificationChannel', secondary=channel_groups, back_populates='shared_groups')
    shared_rules = relationship('AlertRule', secondary=rule_groups, back_populates='shared_groups')

    __table_args__ = (
        Index('idx_groups_tenant_active', 'tenant_id', 'is_active'),
        Index('idx_groups_tenant_name', 'tenant_id', 'name', unique=True),
    )


class UserApiKey(Base):
    """API keys for observability tenants."""
    __tablename__ = 'user_api_keys'

    id = Column(String, primary_key=True, default=generate_uuid)
    tenant_id = Column(String, ForeignKey(TENANTS_ID, ondelete='CASCADE'), nullable=False, index=True)
    user_id = Column(String, ForeignKey(USERS_ID, ondelete='CASCADE'), nullable=False, index=True)
    name = Column(String(100), nullable=False)
    key = Column(String(200), nullable=False, index=True)
    otlp_token = Column(String(200), nullable=True, unique=True, index=True)
    is_default = Column(Boolean, default=False, nullable=False)
    is_enabled = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)

    user = relationship('User', back_populates='api_keys')

    __table_args__ = (
        Index('idx_user_api_keys_user', 'user_id'),
        Index('idx_user_api_keys_tenant', 'tenant_id'),
        Index('idx_user_api_keys_enabled', 'is_enabled'),
        Index('idx_user_api_keys_otlp_token', 'otlp_token'),
    )


class Permission(Base):
    """Permission model for fine-grained access control."""
    __tablename__ = 'permissions'

    id = Column(String, primary_key=True, default=generate_uuid)
    name = Column(String(100), unique=True, nullable=False, index=True)  
    display_name = Column(String(200), nullable=False)
    description = Column(Text)
    resource_type = Column(String(50), nullable=False, index=True)  
    action = Column(String(20), nullable=False, index=True)  
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    groups = relationship('Group', secondary=group_permissions, back_populates='permissions')
    users = relationship('User', secondary=user_permissions, back_populates='permissions')

    __table_args__ = (
        Index('idx_permissions_resource_action', 'resource_type', 'action'),
    )


class AlertRule(Base):
    """Alert rule with tenant and group scoping."""
    __tablename__ = 'alert_rules'

    id = Column(String, primary_key=True, default=generate_uuid)
    tenant_id = Column(String, ForeignKey(TENANTS_ID, ondelete='CASCADE'), nullable=False, index=True)
    created_by = Column(String, ForeignKey(USERS_ID, ondelete=ONDELETE_SET_NULL))
    org_id = Column(String, nullable=True, index=True)  
    name = Column(String(200), nullable=False, index=True)
    group = Column(String(100), nullable=False, default=config.DEFAULT_RULE_GROUP)
    expr = Column(Text, nullable=False)
    duration = Column(String(20), nullable=False, default='5m')
    severity = Column(String(20), nullable=False, default='warning', index=True)
    labels = Column(JSON, default=dict)
    annotations = Column(JSON, default=dict)
    enabled = Column(Boolean, default=True, nullable=False)
    notification_channels = Column(JSON, default=list)  
    visibility = Column(String(20), nullable=False, default='private', index=True)  
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)

    tenant = relationship('Tenant', back_populates='alert_rules')
    creator = relationship('User', foreign_keys=[created_by], back_populates='created_rules')
    shared_groups = relationship('Group', secondary=rule_groups, back_populates='shared_rules')

    __table_args__ = (
        Index('idx_alert_rules_tenant_enabled', 'tenant_id', 'enabled'),
        Index('idx_alert_rules_severity', 'severity'),
        Index('idx_alert_rules_visibility', 'visibility'),
    )


class AlertIncident(Base):
    """Historical alert incidents with lightweight ticket metadata."""
    __tablename__ = 'alert_incidents'

    id = Column(String, primary_key=True, default=generate_uuid)
    tenant_id = Column(String, ForeignKey(TENANTS_ID, ondelete='CASCADE'), nullable=False, index=True)
    fingerprint = Column(String(255), nullable=False, index=True)
    alert_name = Column(String(200), nullable=False, index=True)
    severity = Column(String(20), nullable=False, default='warning', index=True)
    status = Column(String(20), nullable=False, default='open', index=True)
    assignee = Column(String(200), nullable=True)
    notes = Column(JSON, default=list)
    labels = Column(JSON, default=dict)
    annotations = Column(JSON, default=dict)
    starts_at = Column(DateTime, nullable=True, index=True)
    last_seen_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc), index=True)
    resolved_at = Column(DateTime, nullable=True, index=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)

    tenant = relationship('Tenant', back_populates='alert_incidents')

    __table_args__ = (
        Index('idx_alert_incidents_tenant_status', 'tenant_id', 'status'),
        Index('idx_alert_incidents_tenant_fingerprint', 'tenant_id', 'fingerprint', unique=True),
    )


class NotificationChannel(Base):
    """Notification channel with tenant and group scoping."""
    __tablename__ = 'notification_channels'

    id = Column(String, primary_key=True, default=generate_uuid)
    tenant_id = Column(String, ForeignKey(TENANTS_ID, ondelete='CASCADE'), nullable=False, index=True)
    created_by = Column(String, ForeignKey('users.id', ondelete=ONDELETE_SET_NULL))
    name = Column(String(200), nullable=False, index=True)
    type = Column(String(50), nullable=False, index=True)  
    config = Column(JSON, nullable=False, default=dict)
    enabled = Column(Boolean, default=True, nullable=False)
    visibility = Column(String(20), nullable=False, default='private', index=True)  
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)

    tenant = relationship('Tenant', back_populates='notification_channels')
    creator = relationship('User', foreign_keys=[created_by], back_populates='created_channels')
    shared_groups = relationship('Group', secondary=channel_groups, back_populates='shared_channels')

    __table_args__ = (
        Index('idx_notification_channels_tenant_enabled', 'tenant_id', 'enabled'),
        Index('idx_notification_channels_type', 'type'),
        Index('idx_notification_channels_visibility', 'visibility'),
    )


class AuditLog(Base):
    """Audit log for tracking all actions."""
    __tablename__ = 'audit_logs'

    id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(String, ForeignKey(TENANTS_ID, ondelete='CASCADE'), index=True)
    user_id = Column(String, ForeignKey(USERS_ID, ondelete=ONDELETE_SET_NULL), index=True)
    action = Column(String(100), nullable=False, index=True)
    resource_type = Column(String(50), nullable=False, index=True)
    resource_id = Column(String, index=True)
    details = Column(JSON)
    ip_address = Column(String(45))
    user_agent = Column(Text)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False, index=True)

    __table_args__ = (
        Index('idx_audit_logs_tenant_created', 'tenant_id', 'created_at'),
        Index('idx_audit_logs_user_created', 'user_id', 'created_at'),
        Index('idx_audit_logs_action', 'action'),
    )


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

    id = Column(String, primary_key=True, default=generate_uuid)
    tenant_id = Column(String, ForeignKey(TENANTS_ID, ondelete='CASCADE'), nullable=False, index=True)
    created_by = Column(String, ForeignKey(USERS_ID, ondelete=ONDELETE_SET_NULL))
    grafana_uid = Column(String(100), nullable=False, index=True)  
    grafana_id = Column(Integer)  
    title = Column(String(200), nullable=False)
    folder_uid = Column(String(100))  
    visibility = Column(String(20), nullable=False, default='private', index=True)  
    tags = Column(JSON, default=list)
    is_hidden = Column(Boolean, default=False, nullable=False, index=True)  
    hidden_by = Column(JSON, default=list)  
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)


    tenant = relationship('Tenant')
    creator = relationship('User', foreign_keys=[created_by])
    shared_groups = relationship('Group', secondary=dashboard_groups)

    __table_args__ = (
        Index('idx_grafana_dashboards_tenant', 'tenant_id'),
        Index('idx_grafana_dashboards_uid', 'grafana_uid', unique=True),
        Index('idx_grafana_dashboards_visibility', 'visibility'),
    )


class GrafanaDatasource(Base):
    """Grafana datasource ownership and permissions."""
    __tablename__ = 'grafana_datasources'

    id = Column(String, primary_key=True, default=generate_uuid)
    tenant_id = Column(String, ForeignKey(TENANTS_ID, ondelete='CASCADE'), nullable=False, index=True)
    created_by = Column(String, ForeignKey(USERS_ID, ondelete=ONDELETE_SET_NULL))
    grafana_uid = Column(String(100), nullable=False, index=True)  
    grafana_id = Column(Integer)  
    name = Column(String(200), nullable=False)
    type = Column(String(100), nullable=False)  
    visibility = Column(String(20), nullable=False, default='private', index=True)  
    is_hidden = Column(Boolean, default=False, nullable=False, index=True)
    hidden_by = Column(JSON, default=list) 
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)


    tenant = relationship('Tenant')
    creator = relationship('User', foreign_keys=[created_by])
    shared_groups = relationship('Group', secondary=datasource_groups)

    __table_args__ = (
        Index('idx_grafana_datasources_tenant', 'tenant_id'),
        Index('idx_grafana_datasources_uid', 'grafana_uid', unique=True),
        Index('idx_grafana_datasources_visibility', 'visibility'),
    )

