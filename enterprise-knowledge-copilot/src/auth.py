"""
Authentication and authorization system with JWT tokens.
"""
import os
import secrets
from datetime import datetime, timedelta
from typing import Optional, List
from dataclasses import dataclass, field

try:
    from jose import JWTError, jwt
    from passlib.context import CryptContext
    JWT_AVAILABLE = True
except ImportError:
    JWT_AVAILABLE = False


# Configuration
SECRET_KEY = os.getenv("JWT_SECRET_KEY", secrets.token_urlsafe(32))
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24  # 24 hours


@dataclass
class User:
    """User model with role-based access control."""
    username: str
    email: str
    hashed_password: str
    roles: List[str] = field(default_factory=list)  # e.g., ["admin", "user", "readonly"]
    disabled: bool = False
    created_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class TokenData:
    """Decoded JWT token data."""
    username: str
    roles: List[str]
    exp: datetime


class AuthenticationError(Exception):
    """Raised when authentication fails."""
    pass


class AuthorizationError(Exception):
    """Raised when user lacks required permissions."""
    pass


class AuthManager:
    """
    Manages authentication and authorization.
    
    Features:
    - JWT token generation and validation
    - Password hashing with bcrypt
    - Role-based access control (RBAC)
    - In-memory user store (replace with DB in production)
    """
    
    def __init__(self):
        if not JWT_AVAILABLE:
            raise ImportError(
                "JWT authentication requires python-jose and passlib. "
                "Install with: pip install python-jose[cryptography] passlib[bcrypt]"
            )
        
        self.pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
        
        # In-memory user store (replace with database in production)
        self.users: dict[str, User] = {}
        
        # Create default admin user
        self._create_default_users()
    
    def _create_default_users(self):
        """Create default users for development."""
        # Admin user
        self.create_user(
            username="admin",
            email="admin@example.com",
            password="admin123",
            roles=["admin", "user"]
        )
        
        # Regular user
        self.create_user(
            username="user",
            email="user@example.com",
            password="user123",
            roles=["user"]
        )
        
        # Readonly user
        self.create_user(
            username="readonly",
            email="readonly@example.com",
            password="readonly123",
            roles=["readonly"]
        )
    
    def verify_password(self, plain_password: str, hashed_password: str) -> bool:
        """Verify a password against its hash."""
        return self.pwd_context.verify(plain_password, hashed_password)
    
    def get_password_hash(self, password: str) -> str:
        """Hash a password."""
        return self.pwd_context.hash(password)
    
    def create_user(
        self,
        username: str,
        email: str,
        password: str,
        roles: Optional[List[str]] = None
    ) -> User:
        """
        Create a new user.
        
        Args:
            username: Unique username
            email: User email
            password: Plain text password (will be hashed)
            roles: List of roles (default: ["user"])
            
        Returns:
            Created User instance
            
        Raises:
            ValueError: If username already exists
        """
        if username in self.users:
            raise ValueError(f"User {username} already exists")
        
        user = User(
            username=username,
            email=email,
            hashed_password=self.get_password_hash(password),
            roles=roles or ["user"]
        )
        
        self.users[username] = user
        return user
    
    def authenticate_user(self, username: str, password: str) -> Optional[User]:
        """
        Authenticate user with username and password.
        
        Args:
            username: Username
            password: Plain text password
            
        Returns:
            User instance if authentication succeeds, None otherwise
        """
        user = self.users.get(username)
        if not user:
            return None
        if not self.verify_password(password, user.hashed_password):
            return None
        if user.disabled:
            return None
        return user
    
    def create_access_token(
        self,
        username: str,
        roles: List[str],
        expires_delta: Optional[timedelta] = None
    ) -> str:
        """
        Create JWT access token.
        
        Args:
            username: Username
            roles: User roles
            expires_delta: Token expiration time (default: 24 hours)
            
        Returns:
            Encoded JWT token string
        """
        if expires_delta:
            expire = datetime.utcnow() + expires_delta
        else:
            expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
        
        to_encode = {
            "sub": username,
            "roles": roles,
            "exp": expire
        }
        
        encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
        return encoded_jwt
    
    def verify_token(self, token: str) -> TokenData:
        """
        Verify and decode JWT token.
        
        Args:
            token: JWT token string
            
        Returns:
            TokenData with decoded information
            
        Raises:
            AuthenticationError: If token is invalid or expired
        """
        try:
            payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
            username: str = payload.get("sub")
            roles: List[str] = payload.get("roles", [])
            exp: datetime = datetime.fromtimestamp(payload.get("exp"))
            
            if username is None:
                raise AuthenticationError("Invalid token: missing username")
            
            return TokenData(username=username, roles=roles, exp=exp)
        
        except JWTError as e:
            raise AuthenticationError(f"Invalid token: {str(e)}")
    
    def get_user(self, username: str) -> Optional[User]:
        """Get user by username."""
        return self.users.get(username)
    
    def check_permission(self, user: User, required_roles: List[str]) -> bool:
        """
        Check if user has any of the required roles.
        
        Args:
            user: User instance
            required_roles: List of acceptable roles
            
        Returns:
            True if user has at least one required role
        """
        return any(role in user.roles for role in required_roles)
    
    def require_permission(self, user: User, required_roles: List[str]):
        """
        Require user to have specific permissions.
        
        Args:
            user: User instance
            required_roles: List of acceptable roles
            
        Raises:
            AuthorizationError: If user lacks required roles
        """
        if not self.check_permission(user, required_roles):
            raise AuthorizationError(
                f"User {user.username} lacks required roles: {required_roles}"
            )


# Global auth manager instance
_auth_manager: Optional[AuthManager] = None


def get_auth_manager() -> AuthManager:
    """Get or create global auth manager instance."""
    global _auth_manager
    if _auth_manager is None:
        _auth_manager = AuthManager()
    return _auth_manager


# Check if authentication is available
def is_auth_available() -> bool:
    """Check if JWT authentication dependencies are installed."""
    return JWT_AVAILABLE
