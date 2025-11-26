"""
Authentication routes for the Copilot OS API.
"""

from datetime import datetime
from fastapi import APIRouter, Depends, Request, Response, status
from fastapi.security import OAuth2PasswordBearer

from ..core.config import Settings, get_settings
from ..core.exceptions import AuthenticationError
from ..schemas.auth import (
    AuthRequest,
    AuthResponse,
    ForgotPasswordRequest,
    ForgotPasswordResponse,
    RefreshResponse,
    ResetPasswordRequest,
    ResetPasswordResponse,
    TokenRefresh,
)
from ..schemas.user import User as UserSchema, UserCreate
from ..services.auth_service import (
    authenticate_user,
    get_user_profile,
    logout_user,
    refresh_access_token,
    register_user,
)

router = APIRouter(prefix="/auth", tags=["auth"])
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/login", auto_error=False)


def _set_session_cookie(response: Response, token: str, max_age: int, settings: Settings) -> None:
    samesite = (settings.session_cookie_samesite or "lax").lower()
    response.set_cookie(
        key=settings.session_cookie_name,
        value=token,
        max_age=max_age,
        httponly=True,
        secure=settings.session_cookie_secure,
        domain=settings.session_cookie_domain,
        path=settings.session_cookie_path,
        samesite=samesite,
    )


def _clear_session_cookie(response: Response, settings: Settings) -> None:
    response.delete_cookie(
        key=settings.session_cookie_name,
        domain=settings.session_cookie_domain,
        path=settings.session_cookie_path,
    )


@router.post("/register", response_model=AuthResponse, status_code=status.HTTP_201_CREATED)
async def register(payload: UserCreate) -> AuthResponse:
    """Register a new user."""
    return await register_user(payload)


@router.post("/login", response_model=AuthResponse)
async def login(
    payload: AuthRequest,
    response: Response,
    settings: Settings = Depends(get_settings),
) -> AuthResponse:
    """Authenticate a user and issue tokens."""
    auth_response = await authenticate_user(payload.identifier, payload.password)
    _set_session_cookie(response, auth_response.access_token, auth_response.expires_in, settings)
    return auth_response


@router.post("/refresh", response_model=RefreshResponse)
async def refresh(
    payload: TokenRefresh,
    response: Response,
    settings: Settings = Depends(get_settings),
) -> RefreshResponse:
    """Refresh an access token using a refresh token."""
    refreshed = await refresh_access_token(payload.refresh_token)
    _set_session_cookie(response, refreshed.access_token, refreshed.expires_in, settings)
    return refreshed


@router.get("/me", response_model=UserSchema)
async def me(request: Request) -> UserSchema:
    """Retrieve the current authenticated user profile."""
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        raise AuthenticationError("Not authenticated")

    return await get_user_profile(str(user_id))


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    payload: TokenRefresh,
    response: Response,
    token: str = Depends(oauth2_scheme),
    settings: Settings = Depends(get_settings),
) -> None:
    """Logout user and invalidate session.

    P0-LOGOUT-INVALIDATE: Blacklist the refresh token to prevent reuse.
    The access token from the Authorization header is also blacklisted for completeness.
    """
    # Blacklist the refresh token (most important - has longer expiry)
    if payload.refresh_token:
        await logout_user(payload.refresh_token)

    # Also blacklist the access token if provided
    if token:
        await logout_user(token)

    _clear_session_cookie(response, settings)

    return None


@router.post("/forgot-password", response_model=ForgotPasswordResponse, status_code=status.HTTP_200_OK)
async def forgot_password(
    payload: ForgotPasswordRequest,
    settings: Settings = Depends(get_settings)
) -> ForgotPasswordResponse:
    """
    Request password reset email.

    Sends a password reset link to the user's email address.
    The link is valid for 1 hour.
    """
    import structlog
    from ..models.user import User
    from ..models.password_reset import PasswordResetToken
    from ..services.email_service import get_email_service

    logger = structlog.get_logger(__name__)

    # Find user by email
    user = await User.find_one(User.email == payload.email)

    # Always return success to prevent email enumeration
    if not user:
        logger.warning(
            "Password reset requested for non-existent email",
            email=payload.email
        )
        return ForgotPasswordResponse(
            message="Si el correo existe en nuestro sistema, recibirás un enlace de recuperación",
            email=payload.email
        )

    # Invalidate any existing tokens for this user
    existing_tokens = await PasswordResetToken.find(
        PasswordResetToken.user_id == str(user.id),
        PasswordResetToken.used == False
    ).to_list()

    for token in existing_tokens:
        await token.mark_as_used()

    # Create new reset token
    reset_token = PasswordResetToken(
        user_id=str(user.id),
        email=user.email,
        token=PasswordResetToken.generate_token(),
        expires_at=PasswordResetToken.create_expiration(hours=1)
    )
    await reset_token.insert()

    # Generate reset link
    reset_link = f"{settings.password_reset_url_base}/reset-password?token={reset_token.token}"

    # Send email
    email_service = get_email_service()
    email_sent = await email_service.send_password_reset_email(
        to_email=user.email,
        username=user.username,
        reset_link=reset_link
    )

    if not email_sent:
        logger.error(
            "Failed to send password reset email",
            email=user.email,
            user_id=str(user.id)
        )
        # Still return success to user for security
    else:
        logger.info(
            "Password reset email sent",
            email=user.email,
            user_id=str(user.id)
        )

    return ForgotPasswordResponse(
        message="Si el correo existe en nuestro sistema, recibirás un enlace de recuperación",
        email=payload.email
    )


@router.post("/reset-password", response_model=ResetPasswordResponse, status_code=status.HTTP_200_OK)
async def reset_password(
    payload: ResetPasswordRequest,
) -> ResetPasswordResponse:
    """
    Reset password using token from email.

    The token must be valid and not expired (1 hour limit).
    """
    import structlog
    from ..models.password_reset import PasswordResetToken
    from ..models.user import User
    from ..core.exceptions import APIError

    logger = structlog.get_logger(__name__)

    # Find token
    reset_token = await PasswordResetToken.find_one(
        PasswordResetToken.token == payload.token
    )

    if not reset_token:
        logger.warning("Invalid password reset token attempted")
        raise APIError(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Token de recuperación inválido o expirado"
        )

    # Validate token
    if not reset_token.is_valid():
        logger.warning(
            "Expired or used password reset token attempted",
            user_id=reset_token.user_id,
            used=reset_token.used,
            expired=reset_token.expires_at < datetime.utcnow()
        )
        raise APIError(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Token de recuperación inválido o expirado"
        )

    # Find user
    user = await User.get(reset_token.user_id)
    if not user:
        logger.error(
            "Password reset token references non-existent user",
            user_id=reset_token.user_id
        )
        raise APIError(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Token de recuperación inválido"
        )

    # Update password
    from passlib.hash import argon2
    user.hashed_password = argon2.hash(payload.new_password)
    await user.save()

    # Mark token as used
    await reset_token.mark_as_used()

    logger.info(
        "Password successfully reset",
        user_id=str(user.id),
        email=user.email
    )

    return ResetPasswordResponse(
        message="Contraseña actualizada exitosamente. Ahora puedes iniciar sesión con tu nueva contraseña."
    )
