"""
Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
"""

import os

def ensure_test_env() -> None:
    os.environ.setdefault("DATABASE_URL", "postgresql://safeuser:safePass_123@db:5432/beobservant")
    os.environ.setdefault("SKIP_STARTUP_DB_INIT", "1")
    os.environ.setdefault("CORS_ORIGINS", "http://localhost:5173")
    os.environ.setdefault("CORS_ALLOW_CREDENTIALS", "true")
    os.environ.setdefault("JWT_ALGORITHM", "RS256")
