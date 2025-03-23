from typing import Dict, List, Optional, Any
from sqlalchemy.orm import Session
from app.models.position import Position
from datetime import datetime

class RiskService:
    def __init__(self, db: Session):
        self.db = db
    
    def get_position_risk(self, position_id: str) -> Dict[str, Any]:
        """Calculate risk metrics for a specific position"""
        position = self.db.query(Position).filter(Position.id == position_id).first()
        
        if not position:
            return {"error": "Position not found"}
        
        # Calculate Greeks
        delta = self._calculate_delta(position)
        gamma = self._calculate_gamma(position)
        theta = self._calculate_theta(position)
        vega = self._calculate_vega(position)
        
        # Calculate max profit/loss
        max_profit = self._calculate_max_profit(position)
        max_loss = self._calculate_max_loss(position)
        
        # Calculate probability metrics
        probability_profit = self._calculate_probability_profit(position)
        probability_assignment = self._calculate_probability_assignment(position)
        
        return {
            "position_id": position_id,
            "symbol": position.symbol,
            "strategy": position.strategy,
            "risk_level": self._determine_risk_level(position),
            "greeks": {
                "delta": delta,
                "gamma": gamma,
                "theta": theta,
                "vega": vega
            },
            "max_profit": max_profit,
            "max_loss": max_loss,
            "risk_reward_ratio": abs(max_profit / max_loss) if max_loss != 0 else float('inf'),
            "probabilities": {
                "profit": probability_profit,
                "assignment": probability_assignment
            },
            "days_to_expiration": (position.expiration_date - datetime.now()).days
        }
    
    def get_portfolio_risk(self) -> Dict[str, Any]:
        """Calculate portfolio-wide risk metrics"""
        positions = self.db.query(Position).filter(Position.is_open == True).all()
        
        # Calculate sector exposure
        sector_exposure = self._calculate_sector_exposure(positions)
        
        # Calculate strategy distribution
        strategy_distribution = self._calculate_strategy_distribution(positions)
        
        # Calculate expiration distribution
        expiration_distribution = self._calculate_expiration_distribution(positions)
        
        # Calculate overall risk metrics
        total_risk = sum(self._calculate_max_loss(p) for p in positions)
        
        return {
            "totalRisk": total_risk,
            "maxLoss": self._calculate_portfolio_max_loss(positions),
            "diversification": self._calculate_diversification_score(positions),
            "risk_distribution": self._calculate_risk_distribution(positions),
            "sectorExposure": sector_exposure,
            "riskByStrategy": strategy_distribution,
            "riskByExpiration": expiration_distribution
        }
    
    # Private helper methods for risk calculations
    def _calculate_delta(self, position):
        # Placeholder for actual delta calculation logic
        # In a real implementation, this would use option pricing models
        return 0.5  # Placeholder value
    
    def _calculate_gamma(self, position):
        # Placeholder for gamma calculation
        return 0.05  # Placeholder value
    
    def _calculate_theta(self, position):
        # Placeholder for theta calculation
        return -0.1  # Placeholder value
    
    def _calculate_vega(self, position):
        # Placeholder for vega calculation
        return 0.2  # Placeholder value
    
    def _calculate_max_profit(self, position):
        # Logic depends on the strategy
        if position.strategy == "covered_call":
            return position.premium_received
        elif position.strategy == "cash_secured_put":
            return position.premium_received
        return 0
    
    def _calculate_max_loss(self, position):
        # Logic depends on the strategy
        if position.strategy == "covered_call":
            return (position.entry_price * position.quantity) - position.premium_received
        elif position.strategy == "cash_secured_put":
            return (position.strike_price * position.quantity * 100) - position.premium_received
        return 0
    
    def _determine_risk_level(self, position):
        # Logic to determine risk level (low, medium, high, extreme)
        # Based on multiple factors including probability of profit, max loss, etc.
        return "medium"  # Placeholder
    
    def _calculate_probability_profit(self, position):
        # Placeholder for probability calculation
        return 0.65  # Placeholder value
    
    def _calculate_probability_assignment(self, position):
        # Placeholder for assignment probability
        return 0.15  # Placeholder value
    
    def _calculate_sector_exposure(self, positions):
        # Group positions by sector and calculate exposure
        sectors = {}
        total_value = sum(p.entry_price * p.quantity for p in positions)
        
        for position in positions:
            sector = position.sector or "Other"
            if sector not in sectors:
                sectors[sector] = 0
            
            sectors[sector] += (position.entry_price * position.quantity) / total_value * 100
        
        return sectors
    
    def _calculate_strategy_distribution(self, positions):
        # Calculate distribution of risk by strategy
        strategies = {}
        total_risk = sum(self._calculate_max_loss(p) for p in positions)
        
        for position in positions:
            strategy = position.strategy
            if strategy not in strategies:
                strategies[strategy] = 0
            
            strategies[strategy] += self._calculate_max_loss(position) / total_risk * 100 if total_risk else 0
        
        return strategies
    
    def _calculate_expiration_distribution(self, positions):
        # Group positions by expiration timeframe
        today = datetime.now()
        expiration_groups = {
            "< 7 days": 0,
            "7-14 days": 0,
            "15-30 days": 0,
            "> 30 days": 0
        }
        
        total_risk = sum(self._calculate_max_loss(p) for p in positions)
        
        for position in positions:
            days_to_expiration = (position.expiration_date - today).days
            
            if days_to_expiration < 7:
                expiration_groups["< 7 days"] += self._calculate_max_loss(position)
            elif days_to_expiration < 14:
                expiration_groups["7-14 days"] += self._calculate_max_loss(position)
            elif days_to_expiration <= 30:
                expiration_groups["15-30 days"] += self._calculate_max_loss(position)
            else:
                expiration_groups["> 30 days"] += self._calculate_max_loss(position)
        
        # Convert to percentages
        if total_risk > 0:
            for key in expiration_groups:
                expiration_groups[key] = (expiration_groups[key] / total_risk) * 100
        
        return expiration_groups
    
    def _calculate_portfolio_max_loss(self, positions):
        # Calculate the maximum possible loss across all positions
        # This is more complex than just summing individual max losses
        # because positions may have correlations
        
        # Simplified implementation
        return sum(self._calculate_max_loss(p) for p in positions) * 0.8  # Assuming 20% correlation benefit
    
    def _calculate_diversification_score(self, positions):
        # Calculate a diversification score from 0 to 1
        # Higher is better diversified
        
        # Placeholder implementation
        sectors = set(p.sector for p in positions if p.sector)
        num_sectors = len(sectors)
        return min(num_sectors / 10, 1.0)  # Normalize to 0-1
    
    def _calculate_risk_distribution(self, positions):
        # Calculate distribution of positions by risk level
        risk_levels = {
            "low": 0,
            "medium": 0, 
            "high": 0,
            "extreme": 0
        }
        
        for position in positions:
            risk_level = self._determine_risk_level(position)
            risk_levels[risk_level] += 1
        
        # Convert to percentages
        total = len(positions)
        if total > 0:
            for level in risk_levels:
                risk_levels[level] = (risk_levels[level] / total) * 100
        
        return risk_levels