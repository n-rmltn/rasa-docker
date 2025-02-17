import base64
import hashlib
import os
from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple

import jwt
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from dotenv import load_dotenv
from rasa_sdk import Action, Tracker
from rasa_sdk.executor import CollectingDispatcher
from rasa_sdk.events import SlotSet

load_dotenv()

@dataclass
class SecurityConfig:
    """Configuration for security-related operations."""
    jwt_key: str
    encryption_key: str

    @classmethod
    def from_env(cls) -> 'SecurityConfig':
        """Create SecurityConfig from environment variables."""
        jwt_key = os.getenv("JWT_KEY")
        encryption_key = os.getenv("ENCRYPTION_KEY")
        
        if not jwt_key or not encryption_key:
            raise ValueError("Missing required security configuration")
            
        return cls(jwt_key=jwt_key, encryption_key=encryption_key)

class TokenDecoder:
    """Handles JWT token decoding and validation."""
    
    def __init__(self, config: SecurityConfig):
        self.config = config

    def decode_token(self, token: str) -> Dict[str, str]:
        """
        Decode and validate JWT token.
        
        Args:
            token: JWT token string
            
        Returns:
            Dictionary containing decoded claims
            
        Raises:
            ValueError: If token is invalid or expired
        """
        try:
            return jwt.decode(token, self.config.jwt_key, algorithms=['HS256'])
        except jwt.ExpiredSignatureError:
            raise ValueError("Token has expired")
        except jwt.InvalidTokenError:
            raise ValueError("Invalid token")

class ClaimDecryptor:
    """Handles decryption of encrypted claims."""
    
    def __init__(self, config: SecurityConfig):
        """Initialize with encryption key."""
        self.key = self._derive_key(config.encryption_key)

    @staticmethod
    def _derive_key(raw_key: str) -> bytes:
        """
        Derive encryption key using MD5 (maintained for compatibility).
        """
        md5 = hashlib.md5()
        md5.update(raw_key.encode('utf-8'))
        return md5.digest()

    def decrypt(self, encrypted_claim: str) -> str:
        """
        Decrypt an encrypted claim.
        
        Args:
            encrypted_claim: Base64 encoded encrypted claim
            
        Returns:
            Decrypted claim as string
            
        Raises:
            ValueError: If decryption fails
        """
        try:
            # Decode base64
            encrypted_bytes = base64.b64decode(encrypted_claim)
            
            # Create cipher
            cipher = Cipher(
                algorithms.AES(self.key),
                modes.ECB(),  # Note: ECB mode is maintained for compatibility
                backend=default_backend()
            )
            
            # Decrypt
            decryptor = cipher.decryptor()
            decrypted_bytes = decryptor.update(encrypted_bytes) + decryptor.finalize()
            
            # Decode and remove padding
            decrypted_text = decrypted_bytes.decode('utf-8')
            return decrypted_text.rstrip('\x06\t')
            
        except Exception as e:
            raise ValueError(f"Failed to decrypt claim: {str(e)}")

@dataclass
class UserInfo:
    """Structure for storing user information."""
    user_account: str
    role: str

    def to_slots(self) -> list:
        """Convert user info to Rasa slots."""
        return [
            SlotSet("user_account", self.user_account),
            SlotSet("user_role", self.role),
            SlotSet("user_auth", True)
        ]

class InitBot(Action):
    """Rasa action for bot initialization with user authentication."""

    def __init__(self):
        """Initialize with security configuration and handlers."""
        try:
            self.config = SecurityConfig.from_env()
            self.token_decoder = TokenDecoder(self.config)
            self.claim_decryptor = ClaimDecryptor(self.config)
        except ValueError as e:
            raise RuntimeError(f"Failed to initialize InitBot: {str(e)}")

    def name(self) -> str:
        """Return action name."""
        return "action_init_bot"

    def _process_token(self, token: str) -> Optional[UserInfo]:
        """
        Process and validate token, returning user information.
        
        Args:
            token: JWT token string
            
        Returns:
            UserInfo object if successful, None otherwise
        """
        try:
            # Decode token
            decoded_token = self.token_decoder.decode_token(token)
            
            # Decrypt claims
            user_account = self.claim_decryptor.decrypt(decoded_token['user_account'])
            role = self.claim_decryptor.decrypt(decoded_token['role'])
            
            return UserInfo(user_account=user_account, role=role)
            
        except (ValueError, KeyError) as e:
            print(f"Token processing failed: {str(e)}")
            return None

    async def run(
        self,
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: Dict[str, Any]
    ) -> list:
        """Execute the bot initialization action."""
        try:
            # Extract token from entities
            entities = tracker.latest_message.get('entities', [])
            if not entities:
                raise ValueError("No token provided")
                
            token = entities[0].get('value')
            if not token:
                raise ValueError("Invalid token format")

            # Process token and get user info
            user_info = self._process_token(token)
            if not user_info:
                raise ValueError("Failed to process token")

            # Log success (consider using proper logging)
            print(f"User authenticated: {user_info.user_account}")
            
            # Return slots
            return user_info.to_slots()

        except ValueError as e:
            dispatcher.utter_message(text=f"Authentication failed: {str(e)}")
        except Exception as e:
            print(f"Unexpected error during initialization: {str(e)}")
            dispatcher.utter_message(
                text="An unexpected error occurred during initialization. Please try again later."
            )
        
        return []