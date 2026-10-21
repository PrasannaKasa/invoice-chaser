from passlib.context import CryptContext
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired
from app.config import SECRET_KEY

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
serializer = URLSafeTimedSerializer(SECRET_KEY, salt="invoice-chaser-session")

def hash_password(password: str) -> str:
    return pwd_context.hash(password)

def verify_password(password: str, password_hash: str) -> bool:
    return pwd_context.verify(password, password_hash)

def make_session(user_id: int) -> str:
    return serializer.dumps({"user_id": user_id})

def read_session(token: str):
    try:
        data = serializer.loads(token, max_age=60 * 60 * 24 * 7)
        return int(data["user_id"])
    except (BadSignature, SignatureExpired, KeyError, TypeError, ValueError):
        return None
