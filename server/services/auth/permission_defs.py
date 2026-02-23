"""
Scopes and permission definitions for API key management, including listing, creating, updating, deleting API keys, and managing API key shares.

Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
"""

PERMISSION_DEFS = [
    ("read:audit_logs", "Read Audit Logs", "View immutable audit and compliance logs", "audit_logs", "read"),

    ("read:alerts", "Read Alerts", "View alert rules and active alerts", "alerts", "read"),
    ("create:alerts", "Create Alerts", "Create alerts", "alerts", "create"),
    ("update:alerts", "Update Alerts", "Update alerts", "alerts", "update"),
    ("write:alerts", "Write Alerts", "Create and update alert rules", "alerts", "write"),
    ("delete:alerts", "Delete Alerts", "Delete alert rules", "alerts", "delete"),

    ("read:silences", "Read Silences", "View alert silences", "silences", "read"),
    ("create:silences", "Create Silences", "Create alert silences", "silences", "create"),
    ("update:silences", "Update Silences", "Update alert silences", "silences", "update"),
    ("delete:silences", "Delete Silences", "Delete alert silences", "silences", "delete"),

    ("read:rules", "Read Rules", "View alert rules", "rules", "read"),
    ("create:rules", "Create Rules", "Create alert rules", "rules", "create"),
    ("update:rules", "Update Rules", "Update alert rules", "rules", "update"),
    ("delete:rules", "Delete Rules", "Delete alert rules", "rules", "delete"),
    ("test:rules", "Test Rules", "Send test notifications for rules", "rules", "test"),
    ("read:metrics", "Read Metrics", "List metric names for rule creation", "metrics", "read"),

    ("read:channels", "Read Channels", "View notification channels", "channels", "read"),
    ("create:channels", "Create Channels", "Create notification channels", "channels", "create"),
    ("update:channels", "Update Channels", "Update notification channels", "channels", "update"),
    ("write:channels", "Write Channels", "Create and update notification channels", "channels", "write"),
    ("delete:channels", "Delete Channels", "Delete notification channels", "channels", "delete"),
    ("test:channels", "Test Channels", "Send test notifications through channels", "channels", "test"),

    ("read:incidents", "Read Incidents", "View alert incident history", "incidents", "read"),
    ("update:incidents", "Update Incidents", "Update incident assignee, notes, and status", "incidents", "update"),

    ("read:logs", "Read Logs", "Query and view logs", "logs", "read"),
    ("read:traces", "Read Traces", "Query and view traces", "traces", "read"),
    ("read:rca", "Read RCA", "View RCA analysis and reports", "rca", "read"),
    ("create:rca", "Create RCA", "Create RCA analysis jobs", "rca", "create"),

    ("read:dashboards", "Read Dashboards", "View Grafana dashboards", "dashboards", "read"),
    ("create:dashboards", "Create Dashboards", "Create Grafana dashboards", "dashboards", "create"),
    ("update:dashboards", "Update Dashboards", "Update Grafana dashboards", "dashboards", "update"),
    ("write:dashboards", "Write Dashboards", "Create and update dashboards", "dashboards", "write"),
    ("delete:dashboards", "Delete Dashboards", "Delete dashboards", "dashboards", "delete"),

    ("read:datasources", "Read Datasources", "View Grafana datasources", "datasources", "read"),
    ("create:datasources", "Create Datasources", "Create Grafana datasources", "datasources", "create"),
    ("update:datasources", "Update Datasources", "Update Grafana datasources", "datasources", "update"),
    ("delete:datasources", "Delete Datasources", "Delete Grafana datasources", "datasources", "delete"),
    ("query:datasources", "Query Datasources", "Query data through Grafana datasources", "datasources", "query"),

    ("read:folders", "Read Folders", "View Grafana folders", "folders", "read"),
    ("create:folders", "Create Folders", "Create Grafana folders", "folders", "create"),
    ("delete:folders", "Delete Folders", "Delete Grafana folders", "folders", "delete"),

    ("read:agents", "Read Agents", "View OTEL agents and system metrics", "agents", "read"),

    ("read:api_keys", "Read API Keys", "View API keys", "api_keys", "read"),
    ("create:api_keys", "Create API Keys", "Create API keys", "api_keys", "create"),
    ("update:api_keys", "Update API Keys", "Update API keys", "api_keys", "update"),
    ("delete:api_keys", "Delete API Keys", "Delete API keys", "api_keys", "delete"),

    ("create:users", "Create Users", "Create user accounts", "users", "create"),
    ("update:users", "Update Users", "Update user accounts", "users", "update"),
    ("delete:users", "Delete Users", "Delete user accounts", "users", "delete"),
    ("update:user_permissions", "Update User Permissions", "Update direct user permissions", "users", "update_permissions"),
    ("manage:users", "Manage Users", "Create, update, and delete users", "users", "manage"),
    ("read:users", "Read Users", "View user information", "users", "read"),

    ("create:groups", "Create Groups", "Create groups", "groups", "create"),
    ("update:groups", "Update Groups", "Update groups", "groups", "update"),
    ("delete:groups", "Delete Groups", "Delete groups", "groups", "delete"),
    ("update:group_permissions", "Update Group Permissions", "Update group permissions", "groups", "update_permissions"),
    ("update:group_members", "Update Group Members", "Update group members", "groups", "update_members"),
    ("manage:groups", "Manage Groups", "Create, update, and delete groups", "groups", "manage"),
    ("read:groups", "Read Groups", "View group information", "groups", "read"),

    ("manage:tenants", "Manage Tenants", "Manage tenant settings", "tenants", "manage"),
]
