"""
Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
"""

import unittest
import inspect

from main import lifespan

class LifespanTests(unittest.TestCase):
    def test_lifespan_uses_asyncio_sleep_not_time_sleep(self):
        src = inspect.getsource(lifespan)
        self.assertNotIn("time.sleep", src)
        self.assertIn("asyncio.sleep", src)
        self.assertNotIn("SessionLocal", src)
        self.assertNotIn("_validate_schema", src)
        self.assertIn("AUTH_API_URL", src)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
