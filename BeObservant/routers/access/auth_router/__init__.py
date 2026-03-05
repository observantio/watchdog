"""
Composed access/auth router split by concern.
"""

from .shared import router
from . import api_keys  
from . import audit 
from . import authentication 
from . import groups  
from . import mfa 
from . import users 

__all__ = ["router"]
