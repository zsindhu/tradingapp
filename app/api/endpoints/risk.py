from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.services.risk import RiskService
from app.core.security import get_current_user, User

router = APIRouter()

@router.get("/portfolio")
async def get_portfolio_risk(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get risk analysis for the entire portfolio"""
    risk_service = RiskService(db)
    return risk_service.get_portfolio_risk()

@router.get("/positions/{position_id}")
async def get_position_risk(
    position_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get risk analysis for a specific position"""
    risk_service = RiskService(db)
    risk_data = risk_service.get_position_risk(position_id)
    
    if "error" in risk_data:
        raise HTTPException(status_code=404, detail=risk_data["error"])
    
    return risk_data