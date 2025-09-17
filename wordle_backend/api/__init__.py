"""
API package for Wordle backend.

Exports common constants used across serializers and views.
"""

# PUBLIC_INTERFACE
def get_package_info():
    """Return brief metadata about this package."""
    return {"name": "api", "description": "Wordle backend API app"}

# Guess scoring result constants
RESULT_CORRECT = "correct"
RESULT_PRESENT = "present"
RESULT_ABSENT = "absent"
