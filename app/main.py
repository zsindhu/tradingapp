from fastapi import FastAPI, Depends, HTTPException, status, Request, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse
from pydantic import BaseModel
import httpx
import os
from typing import List, Optional
import json
from datetime import datetime, timedelta
import secrets
from authlib.integrations.starlette_client import OAuth, OAuthError
from starlette.config import Config
from starlette.middleware.sessions import SessionMiddleware
from app.database import engine, get_db, Base
from app.models import Position as DBPosition
from sqlalchemy.orm import Session
from sqlalchemy import text
from sqlalchemy import inspect
from app.api import router as api_router
import logging
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
import random
from app.alerts import router as alerts_router
from app.watchlist import router as watchlist_router
from app.notifications import router as notifications_router
from app.market_data import router as market_data_router
from app.risk import router as risk_router
from app.analytics import router as analytics_router
from app.scanner import router as scanner_router
import asyncio
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from app.market_data.service import update_all_cached_data
from sqlalchemy import Column, Boolean, String, Text, DateTime
from app.schwab import router as schwab_router
from app.strategy import router as strategy_router
from app.auth import DEV_MODE, get_current_user, get_optional_user, User, oauth2_scheme, get_token
from app.config import BASE_URL, FRONTEND_URLS

# app/main.py (update to include versioning)
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.core.config import settings

# Import routers
from app.api.endpoints import positions, auth, market_data, alerts, risk, analytics

app = FastAPI(title=settings.APP_NAME)

# Enable CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.FRONTEND_URLS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Dev-Mode"],
)

# API v1 router
from fastapi import APIRouter

api_v1_router = APIRouter(prefix="/api/v1")
api_v1_router.include_router(positions.router, prefix="/positions", tags=["positions"])
api_v1_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_v1_router.include_router(market_data.router, prefix="/market-data", tags=["market-data"])
api_v1_router.include_router(alerts.router, prefix="/alerts", tags=["alerts"])
api_v1_router.include_router(risk.router, prefix="/risk", tags=["risk"])
api_v1_router.include_router(analytics.router, prefix="/analytics", tags=["analytics"])

# Maintain backward compatibility with original routes
app.include_router(api_v1_router)

# Legacy router (without the /v1 prefix)
api_legacy_router = APIRouter(prefix="/api")
api_legacy_router.include_router(positions.router, prefix="/positions", tags=["positions"])
api_legacy_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_legacy_router.include_router(market_data.router, prefix="/market-data", tags=["market-data"])
api_legacy_router.include_router(alerts.router, prefix="/alerts", tags=["alerts"])
api_legacy_router.include_router(risk.router, prefix="/risk", tags=["risk"])
api_legacy_router.include_router(analytics.router, prefix="/analytics", tags=["analytics"])

app.include_router(api_legacy_router)

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# Create database tables
try:
    Base.metadata.create_all(bind=engine)
    logger.info("Database tables created")
except Exception as e:
    logger.error(f"Error creating database tables: {str(e)}")

app = FastAPI(title="Premium Trader API")

# Enable CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=FRONTEND_URLS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Dev-Mode"],
)

# Add session middleware for OAuth
app.add_middleware(SessionMiddleware, secret_key=os.environ.get("SECRET_KEY", secrets.token_urlsafe(32)))

# Configure OAuth
config = Config(".env")  # Load from .env file
oauth = OAuth(config)

# Configure Schwab OAuth
oauth.register(
    name="schwab",
    client_id=os.environ.get("SCHWAB_CLIENT_ID", "p3DmGsTGxNL1qE7PZA0rO2T6P1f4dxoX"),
    client_secret=os.environ.get("SCHWAB_CLIENT_SECRET", "yadcm83LhiRFWb3E"),
    authorize_url="https://api.schwab.com/oauth/authorize",
    access_token_url="https://api.schwab.com/oauth/token",
    api_base_url="https://api.schwab.com/",
    client_kwargs={"scope": "accounts positions orders"},
)

# In-memory token storage (use a database in production)
tokens = {}

# Models
class Position(BaseModel):
    id: Optional[str] = None
    symbol: str
    strategy: str  # 'covered_call' or 'cash_secured_put'
    quantity: int
    entry_price: float
    entry_date: datetime
    expiration_date: datetime
    strike_price: float
    premium_received: float
    status: str = "open"  # 'open' or 'closed'
    close_price: Optional[float] = None
    close_date: Optional[datetime] = None
    profit_loss: Optional[float] = None
    notes: Optional[str] = None
    is_open: bool = True
    sector: Optional[str] = None

class PositionCreate(BaseModel):
    symbol: str
    strategy: str
    quantity: int
    entry_price: float
    entry_date: datetime
    expiration_date: datetime
    strike_price: float
    premium_received: float
    notes: Optional[str] = None

class PositionClose(BaseModel):
    close_price: float
    close_date: datetime = datetime.now()
    notes: Optional[str] = None

# Add a Token model for persistent storage
class OAuthToken(Base):
    __tablename__ = "oauth_tokens"
    
    user_id = Column(String, primary_key=True)
    access_token = Column(Text)
    refresh_token = Column(Text)
    expires_at = Column(DateTime)
    token_type = Column(String)
    scope = Column(String)
    is_active = Column(Boolean, default=True)

# Routes
@app.get("/")
async def root():
    """Root endpoint"""
    return {"message": "Welcome to Premium Trader API"}

@app.get("/health")
async def health_check():
    """Health check endpoint for monitoring"""
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "dev_mode": DEV_MODE,
        "base_url": BASE_URL
    }

@app.get("/dev-mode")
async def dev_mode_status():
    """Check if development mode is enabled"""
    return {"dev_mode": DEV_MODE}

# Auth routes
@app.get("/auth/login")
async def login(request: Request):
    """Initiate OAuth flow with Schwab"""
    redirect_uri = request.url_for("auth_callback")
    return await oauth.schwab.authorize_redirect(request, redirect_uri)

@app.get("/auth/callback")
async def auth_callback(request: Request, db: Session = Depends(get_db)):
    """Handle OAuth callback from Schwab"""
    try:
        token = await oauth.schwab.authorize_access_token(request)
        
        # Get user info from Schwab API
        client = oauth.schwab.get_client(token=token)
        resp = await client.get("user")
        user_info = resp.json()
        
        # Store token in database
        user_id = user_info.get("user_id", "default_user")
        
        # Check if token exists
        db_token = db.query(OAuthToken).filter(OAuthToken.user_id == user_id).first()
        
        if db_token:
            # Update existing token
            db_token.access_token = token["access_token"]
            db_token.refresh_token = token.get("refresh_token")
            db_token.expires_at = datetime.now() + timedelta(seconds=token["expires_in"])
            db_token.token_type = token["token_type"]
            db_token.scope = token.get("scope", "")
            db_token.is_active = True
        else:
            # Create new token
            db_token = OAuthToken(
                user_id=user_id,
                access_token=token["access_token"],
                refresh_token=token.get("refresh_token"),
                expires_at=datetime.now() + timedelta(seconds=token["expires_in"]),
                token_type=token["token_type"],
                scope=token.get("scope", "")
            )
            db.add(db_token)
        
        db.commit()
        
        # Redirect to frontend with success
        frontend_url = os.environ.get("FRONTEND_URL", "http://localhost:3000")
        return RedirectResponse(f"{frontend_url}/auth-success?token={token['access_token']}")
        
    except OAuthError as error:
        logger.error(f"OAuth error: {str(error)}")
        return {"error": str(error)}

# Helper function to get token
async def get_token(user_id: str = "current_user"):
    # In development mode, return a dummy token if no real token exists
    if DEV_MODE and user_id not in tokens:
        logger.warning("Using development mode token bypass")
        return {
            "access_token": "dev_token",
            "token_type": "bearer",
            "expires_at": (datetime.now() + timedelta(hours=1)).timestamp()
        }
        
    if user_id not in tokens:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated"
        )
    
    token = tokens[user_id]
    
    # Check if token is expired and refresh if needed
    if datetime.now() > datetime.fromtimestamp(token.get("expires_at", 0)):
        async with httpx.AsyncClient() as client:
            refresh_token = token.get("refresh_token")
            if not refresh_token:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Session expired. Please log in again."
                )
            
            refresh_response = await client.post(
                oauth.schwab.access_token_url,
                data={
                    "grant_type": "refresh_token",
                    "refresh_token": refresh_token,
                    "client_id": os.environ.get("SCHWAB_CLIENT_ID"),
                    "client_secret": os.environ.get("SCHWAB_CLIENT_SECRET"),
                }
            )
            
            new_token = refresh_response.json()
            new_token["expires_at"] = datetime.now().timestamp() + new_token.get("expires_in", 3600)
            tokens[user_id] = new_token
            token = new_token
    
    return token

# Schwab API routes
@app.get("/api/accounts")
async def get_accounts(token: dict = Depends(get_token)):
    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"{oauth.schwab.api_base_url}v1/accounts",
            headers={"Authorization": f"Bearer {token['access_token']}"}
        )
        
        if response.status_code != 200:
            raise HTTPException(
                status_code=response.status_code,
                detail=f"Schwab API error: {response.text}"
            )
        
        return response.json()

@app.get("/api/positions")
async def get_positions(account_id: str, token: dict = Depends(get_token)):
    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"{oauth.schwab.api_base_url}v1/accounts/{account_id}/positions",
            headers={"Authorization": f"Bearer {token['access_token']}"}
        )
        
        if response.status_code != 200:
            raise HTTPException(
                status_code=response.status_code,
                detail=f"Schwab API error: {response.text}"
            )
        
        schwab_positions = response.json()
        
        # Transform Schwab positions to app positions
        app_positions = []
        for pos in schwab_positions.get("positions", []):
            # Filter for options positions
            if pos.get("instrument", {}).get("assetType") == "OPTION":
                option_data = pos.get("instrument", {})
                
                # Determine if it's a covered call or cash secured put
                option_type = option_data.get("putCall")
                strategy = "covered_call" if option_type == "CALL" else "cash_secured_put"
                
                # Create position object
                app_position = Position(
                    id=pos.get("positionId"),
                    symbol=option_data.get("underlyingSymbol"),
                    strategy=strategy,
                    quantity=pos.get("longQuantity") or pos.get("shortQuantity"),
                    entry_price=pos.get("averagePrice"),
                    entry_date=datetime.fromisoformat(pos.get("acquiredDate").replace("Z", "+00:00")),
                    expiration_date=datetime.fromisoformat(option_data.get("expirationDate").replace("Z", "+00:00")),
                    strike_price=float(option_data.get("strikePrice")),
                    premium_received=abs(float(pos.get("averagePrice")) * 100),
                    status="open",
                    notes=f"Imported from Schwab on {datetime.now().strftime('%Y-%m-%d')}"
                )
                app_positions.append(app_position)
        
        return {"positions": [pos.dict() for pos in app_positions]}

@app.post("/api/positions")
async def create_position(position: PositionCreate, token: dict = Depends(get_token)):
    # Here you would typically create an order in Schwab
    # For now, we'll just return a mock response
    new_position = Position(
        id=f"pos_{secrets.token_hex(8)}",
        **position.dict()
    )
    
    return new_position.dict()

@app.put("/api/positions/{position_id}/close")
async def close_position(position_id: str, close_data: PositionClose, token: dict = Depends(get_token)):
    # Here you would typically close the position in Schwab
    # For now, we'll just return a mock response
    
    # In a real implementation, you would:
    # 1. Get the position from your database
    # 2. Calculate P&L
    # 3. Update the position status
    # 4. Create a closing order in Schwab if needed
    
    # Mock response
    return {
        "id": position_id,
        "status": "closed",
        "close_price": close_data.close_price,
        "close_date": close_data.close_date,
        "profit_loss": 250.00,  # Mock value
        "notes": close_data.notes
    }

@app.delete("/api/positions/{position_id}")
async def delete_position(position_id: str, token: dict = Depends(get_token)):
    # Here you would typically delete the position from your database
    # For now, we'll just return a success response
    return {"success": True, "message": f"Position {position_id} deleted"}

# Analytics endpoints
@app.get("/api/analytics/summary")
async def get_analytics_summary(token: dict = Depends(get_token)):
    # In a real implementation, you would calculate these metrics from your positions data
    return {
        "total_profit": 3250.75,
        "win_rate": 0.78,
        "profit_factor": 2.3,
        "average_win": 425.50,
        "average_loss": 185.25,
        "total_trades": 45,
        "winning_trades": 35,
        "losing_trades": 10,
        "open_positions": 8
    }

@app.get("/healthcheck")
async def healthcheck(db: Session = Depends(get_db)):
    try:
        db.execute(text("SELECT 1"))
        return {"status": "ok", "message": "Service is running, database connected"}
    except Exception as e:
        logger.error(f"Database healthcheck failed: {str(e)}")
        return {"status": "error", "message": f"Database error: {str(e)}"}

@app.get("/users/me")
async def read_users_me(current_user: User = Depends(get_current_user)):
    return current_user

# Add a background task to fetch market data
def fetch_market_data(symbols):
    """Background task to fetch market data for a list of symbols"""
    # In a real implementation, you would call a market data API
    # For now, we'll return mock data
    market_data = {}
    for symbol in symbols:
        market_data[symbol] = {
            "price": 150.25,  # Mock price
            "change": 2.5,    # Mock change
            "change_percent": 1.7,  # Mock percent change
            "volume": 1500000,  # Mock volume
            "timestamp": datetime.now().isoformat()
        }
    return market_data

@app.get("/api/market-data")
async def get_market_data(symbols: str, background_tasks: BackgroundTasks):
    """Get market data for a list of symbols"""
    symbol_list = symbols.split(",")
    background_tasks.add_task(fetch_market_data, symbol_list)
    
    # Return immediately with a task ID
    # In a real implementation, you would store the result and provide a way to retrieve it
    return {"task_id": secrets.token_hex(8), "status": "processing"}

@app.get("/api/option-chain/{symbol}")
async def get_option_chain(symbol: str, token: dict = Depends(get_token)):
    """Get option chain data for a symbol"""
    try:
        # In a real implementation, you would call the Schwab API or another options data provider
        # For now, we'll return mock data
        
        # Get current date and generate expiration dates
        today = datetime.now()
        expirations = [
            (today + timedelta(days=7)).strftime("%Y-%m-%d"),
            (today + timedelta(days=14)).strftime("%Y-%m-%d"),
            (today + timedelta(days=30)).strftime("%Y-%m-%d"),
            (today + timedelta(days=60)).strftime("%Y-%m-%d"),
            (today + timedelta(days=90)).strftime("%Y-%m-%d"),
        ]
        
        # Mock current stock price
        current_price = 150.25
        
        # Generate mock option chain
        strikes = [
            current_price - 15,
            current_price - 10,
            current_price - 5,
            current_price,
            current_price + 5,
            current_price + 10,
            current_price + 15,
        ]
        
        calls = []
        puts = []
        
        for expiration in expirations:
            for strike in strikes:
                # Calculate mock option prices
                days_to_expiration = (datetime.strptime(expiration, "%Y-%m-%d") - today).days
                call_price = max(0.05, (current_price - strike) + (strike * 0.02 * (days_to_expiration / 365)))
                put_price = max(0.05, (strike - current_price) + (strike * 0.02 * (days_to_expiration / 365)))
                
                # Add call option
                calls.append({
                    "symbol": f"{symbol}_{expiration}C{strike}",
                    "strike": strike,
                    "expiration": expiration,
                    "bid": round(call_price - 0.05, 2),
                    "ask": round(call_price + 0.05, 2),
                    "last": round(call_price, 2),
                    "volume": random.randint(10, 1000),
                    "open_interest": random.randint(100, 5000),
                    "delta": round(0.5 + ((current_price - strike) / current_price) * 0.5, 2),
                    "gamma": round(0.02 * (1 - ((current_price - strike) / current_price) ** 2), 3),
                    "theta": round(-0.01 * (days_to_expiration ** 0.5), 3),
                    "vega": round(0.1 * (days_to_expiration / 365) ** 0.5, 3),
                    "implied_volatility": round(0.3 + random.random() * 0.2, 2)
                })
                
                # Add put option
                puts.append({
                    "symbol": f"{symbol}_{expiration}P{strike}",
                    "strike": strike,
                    "expiration": expiration,
                    "bid": round(put_price - 0.05, 2),
                    "ask": round(put_price + 0.05, 2),
                    "last": round(put_price, 2),
                    "volume": random.randint(10, 1000),
                    "open_interest": random.randint(100, 5000),
                    "delta": round(-0.5 + ((strike - current_price) / current_price) * 0.5, 2),
                    "gamma": round(0.02 * (1 - ((strike - current_price) / current_price) ** 2), 3),
                    "theta": round(-0.01 * (days_to_expiration ** 0.5), 3),
                    "vega": round(0.1 * (days_to_expiration / 365) ** 0.5, 3),
                    "implied_volatility": round(0.3 + random.random() * 0.2, 2)
                })
        
        return {
            "symbol": symbol,
            "price": current_price,
            "updated_at": datetime.now().isoformat(),
            "expirations": expirations,
            "strikes": strikes,
            "calls": calls,
            "puts": puts
        }
    except Exception as e:
        logger.error(f"Error getting option chain: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

# Include the API router
app.include_router(api_router, prefix="/api")
app.include_router(alerts_router, prefix="/api/alerts", tags=["alerts"])
app.include_router(watchlist_router, prefix="/api/watchlist", tags=["watchlist"])
app.include_router(notifications_router, prefix="/api/notifications", tags=["notifications"])
app.include_router(market_data_router, prefix="/api/market-data", tags=["market-data"])
app.include_router(risk_router, prefix="/api/risk", tags=["risk"])
app.include_router(analytics_router, prefix="/api/analytics", tags=["analytics"])
app.include_router(scanner_router, prefix="/api/scanner", tags=["scanner"])
app.include_router(schwab_router, prefix="/api/schwab", tags=["schwab"])
app.include_router(strategy_router, prefix="/api/strategy", tags=["strategy"])

# Background task to check for alerts
async def check_alerts_task():
    """Background task to periodically check for alerts"""
    while True:
        try:
            async with httpx.AsyncClient() as client:
                # Use the BASE_URL for internal API calls
                response = await client.get(f"{BASE_URL}/api/alerts/check")
                
                if response.status_code == 200:
                    triggered_alerts = response.json()
                    
                    if triggered_alerts:
                        # Process the triggered alerts
                        await client.post(f"{BASE_URL}/api/notifications/process-alerts")
                        
                        logger.info(f"Processed {len(triggered_alerts)} triggered alerts")
            
            # Wait for 15 minutes before checking again
            await asyncio.sleep(15 * 60)
        except Exception as e:
            logger.error(f"Error in check_alerts_task: {str(e)}")
            # Wait for 1 minute before retrying
            await asyncio.sleep(60)

# Start the background task when the app starts
@app.on_event("startup")
async def startup_event():
    asyncio.create_task(check_alerts_task())
    
    # Set up scheduler for market data updates
    scheduler = AsyncIOScheduler()
    
    # Schedule market data updates every 15 minutes during market hours
    scheduler.add_job(
        update_market_data_task,
        'cron',
        day_of_week='mon-fri',
        hour='9-16',  # 9 AM to 4 PM (market hours)
        minute='*/15',  # Every 15 minutes
        timezone='America/New_York'
    )
    
    scheduler.start()

async def update_market_data_task():
    """Background task to update market data"""
    try:
        # Get all symbols from positions and watchlist
        async with httpx.AsyncClient() as client:
            response = await client.post(f"{BASE_URL}/api/market-data/update-cache")
            logger.info("Market data update triggered")
    except Exception as e:
        logger.error(f"Error in update_market_data_task: {str(e)}")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)

#print schema
@app.on_event("startup")
async def print_schema():
    inspector = inspect(engine)
    tables = inspector.get_table_names()
    for table in tables:
        print(f"Table: {table}")
        for column in inspector.get_columns(table):
            print(f"  {column['name']}: {column['type']}")

@app.on_event("startup")
async def refresh_metadata():
    from sqlalchemy import inspect
    inspector = inspect(engine)
    inspector.clear_cache()
    logger.info("SQLAlchemy metadata cache cleared")

# Add development mode warning middleware
@app.middleware("http")
async def dev_mode_warning(request: Request, call_next):
    """Add a warning header in development mode"""
    response = await call_next(request)
    if DEV_MODE:
        response.headers["X-Dev-Mode"] = "True"
    return response

# Add a configuration endpoint to help with debugging
@app.get("/api/config")
async def get_config():
    """Get server configuration for debugging"""
    if not DEV_MODE:
        raise HTTPException(status_code=403, detail="Only available in development mode")
    
    return {
        "base_url": BASE_URL,
        "dev_mode": DEV_MODE,
        "allowed_origins": FRONTEND_URLS,
        "server_time": datetime.now().isoformat()
    }
