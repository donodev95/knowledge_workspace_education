from typing import Annotated

from fastapi import Request, Depends
from backend.app.core.config import Settings
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from backend.app.auth.security import decode_access_token, InvalidTokenError
from backend.app.db.session import DatabaseDep
from backend.app.models import User



def get_request_settings(request: Request) -> Settings:
    """Return settings loaded during application startup."""
    settings: Settings = request.app.state.settings
    return settings


SettingsDep = Annotated[Settings, Depends(get_request_settings)]

bearer = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
    database: DatabaseDep,
    settings: SettingsDep,
) -> User:
    unauthorized = HTTPException(401, 'Invalid or missing access token', headers={'WWW-Authenticate': 'Bearer'})
    if credentials is None:
        raise unauthorized
    try:
        claims = decode_access_token(credentials.credentials, settings)
    except InvalidTokenError:
        raise unauthorized
    async with database.sessions() as session:
        user = await session.get(User, claims.user_id)
        if user is None or not user.is_active:
            raise unauthorized
        return user


CurrentUserDep = Annotated[User, Depends(get_current_user)]
