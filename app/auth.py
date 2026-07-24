import secrets
from fastapi import Request, HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.config import get_settings
from app.database import get_db
from app.models import Experimenter

security_scheme = HTTPBearer(auto_error=False)


def verify_pipeline_token(credentials: HTTPAuthorizationCredentials | None = Depends(security_scheme)):
    """Verify Bearer PIPELINE_TOKEN for pipeline endpoints."""
    if not credentials:
        raise HTTPException(status_code=401, detail="Missing token")
    if not secrets.compare_digest(credentials.credentials, get_settings().pipeline_token):
        raise HTTPException(status_code=401, detail="Invalid pipeline token")
    return True


# Admin session: store logged-in user id in request.session
ADMIN_SESSION_KEY = "experimenter_id"


async def get_current_user(request: Request, db: AsyncSession = Depends(get_db)):
    """Authenticate from session cookie. Returns Experimenter or raises 401."""
    user_id = request.session.get(ADMIN_SESSION_KEY)
    if not user_id:
        raise HTTPException(status_code=401, detail="Not logged in")
    stmt = select(Experimenter).where(Experimenter.id == user_id, Experimenter.is_active == True)
    result = await db.execute(stmt)
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=401, detail="Invalid session")
    return user


def require_admin(user: Experimenter = Depends(get_current_user)):
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin only")
    return user
