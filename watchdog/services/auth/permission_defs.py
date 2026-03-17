"""
Scopes and permission definitions for API key management, including listing, creating, updating, deleting API keys, and managing API key shares.

Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
"""

PERMISSION_DEFS = [
    ("read:audit_logs", "Read Audit Logs", "View audit and compliance logs", "audit_logs", "read"),

    ("read:alerts", "Read Alerts", "See alert rules and active alerts", "alerts", "read"),
    ("create:alerts", "Create Alerts", "Create alert rules", "alerts", "create"),
    ("update:alerts", "Update Alerts", "Modify alerts", "alerts", "update"),
    ("write:alerts", "Write Alerts", "Create or modify alert rules", "alerts", "write"),
    ("delete:alerts", "Delete Alerts", "Remove alert rules", "alerts", "delete"),

    ("read:silences", "Read Silences", "See alert silences", "silences", "read"),
    ("create:silences", "Create Silences", "Create an alert silence", "silences", "create"),
    ("update:silences", "Update Silences", "Edit an alert silence", "silences", "update"),
    ("delete:silences", "Delete Silences", "Remove an alert silence", "silences", "delete"),

    ("read:rules", "Read Rules", "See alert rules", "rules", "read"),
    ("create:rules", "Create Rules", "Create an alert rule", "rules", "create"),
    ("update:rules", "Update Rules", "Edit an alert rule", "rules", "update"),
    ("delete:rules", "Delete Rules", "Remove an alert rule", "rules", "delete"),
    ("test:rules", "Test Rules", "Trigger rule test notifications", "rules", "test"),
    ("read:metrics", "Read Metrics", "List metrics for rules", "metrics", "read"),

    ("read:channels", "Read Channels", "See notification channels", "channels", "read"),
    ("create:channels", "Create Channels", "Create a notification channel", "channels", "create"),
    ("update:channels", "Update Channels", "Edit a notification channel", "channels", "update"),
    ("write:channels", "Write Channels", "Create or edit channels", "channels", "write"),
    ("delete:channels", "Delete Channels", "Remove a channel", "channels", "delete"),
    ("test:channels", "Test Channels", "Send test notifications", "channels", "test"),

    ("read:incidents", "Read Incidents", "See incident history", "incidents", "read"),
    ("update:incidents", "Update Incidents", "Modify incident details", "incidents", "update"),

    ("read:logs", "Read Logs", "Query and view logs", "logs", "read"),
    ("read:traces", "Read Traces", "Query and view traces", "traces", "read"),
    ("read:rca", "Read RCA", "View RCA analyses and reports", "rca", "read"),
    ("create:rca", "Create RCA", "Start RCA analysis jobs", "rca", "create"),
    ("delete:rca", "Delete RCA", "Delete your RCA reports", "rca", "delete"),

    ("read:dashboards", "Read Dashboards", "View Grafana dashboards", "dashboards", "read"),
    ("create:dashboards", "Create Dashboards", "Create Grafana dashboards", "dashboards", "create"),
    ("update:dashboards", "Update Dashboards", "Edit dashboards", "dashboards", "update"),
    ("write:dashboards", "Write Dashboards", "Create or edit dashboards", "dashboards", "write"),
    ("delete:dashboards", "Delete Dashboards", "Remove dashboards", "dashboards", "delete"),

    ("read:datasources", "Read Datasources", "View Grafana datasources", "datasources", "read"),
    ("create:datasources", "Create Datasources", "Add a Grafana datasource", "datasources", "create"),
    ("update:datasources", "Update Datasources", "Edit Grafana datasources", "datasources", "update"),
    ("delete:datasources", "Delete Datasources", "Remove Grafana datasources", "datasources", "delete"),
    ("query:datasources", "Query Datasources", "Query through datasources", "datasources", "query"),

    ("read:folders", "Read Folders", "View Grafana folders", "folders", "read"),
    ("create:folders", "Create Folders", "Create Grafana folders", "folders", "create"),
    ("delete:folders", "Delete Folders", "Delete Grafana folders", "folders", "delete"),

    ("read:agents", "Read Agents", "View OTEL agents and metrics", "agents", "read"),

    ("read:api_keys", "Read API Keys", "View API keys", "api_keys", "read"),
    ("create:api_keys", "Create API Keys", "Create API keys", "api_keys", "create"),
    ("update:api_keys", "Update API Keys", "Edit API keys", "api_keys", "update"),
    ("delete:api_keys", "Delete API Keys", "Remove API keys", "api_keys", "delete"),

    ("create:users", "Create Users", "Create user accounts", "users", "create"),
    ("update:users", "Update Users", "Edit user accounts", "users", "update"),
    ("delete:users", "Delete Users", "Remove user accounts", "users", "delete"),
    ("update:user_permissions", "Update User Permissions", "Change a user's permissions", "users", "update_permissions"),
    ("manage:users", "Manage Users", "Manage user accounts", "users", "manage"),
    ("read:users", "Read Users", "View user info", "users", "read"),

    ("create:groups", "Create Groups", "Create groups", "groups", "create"),
    ("update:groups", "Update Groups", "Edit groups", "groups", "update"),
    ("delete:groups", "Delete Groups", "Remove groups", "groups", "delete"),
    ("update:group_permissions", "Update Group Permissions", "Change group permissions", "groups", "update_permissions"),
    ("update:group_members", "Update Group Members", "Change group members", "groups", "update_members"),
    ("manage:groups", "Manage Groups", "Manage groups", "groups", "manage"),
    ("read:groups", "Read Groups", "View group info", "groups", "read"),

    ("manage:tenants", "Manage Tenants", "Manage tenant settings", "tenants", "manage"),
]
