"""Practice scenarios: the library coaches browse and preview. Scoring happens in the app."""
from fastapi import APIRouter, Depends
from ..auth import current_user
from ..models import User
from .. import practice

router = APIRouter(tags=["practice"])


@router.get("/practice/scenarios")
def scenario_library(user: User = Depends(current_user)):
    """Every topic with its stages, and every scenario with its pitch filled in from its format."""
    return practice.library()
