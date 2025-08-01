"""
PlexSync - Retry Mechanisms
Robust retry logic with exponential backoff and intelligent error recovery.
"""

import time
import random
import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, Any, List, Optional, Dict, Type
from functools import wraps


class ErrorType(Enum):
    """Types of errors that can occur during sync"""
    NETWORK = "network"
    PERMISSION = "permission"
    DISK_FULL = "disk_full"
    FILE_LOCKED = "file_locked"
    TIMEOUT = "timeout"
    CORRUPTION = "corruption"
    UNKNOWN = "unknown"


class RetryStrategy(Enum):
    """Retry strategies"""
    FIXED = "fixed"
    EXPONENTIAL = "exponential"
    LINEAR = "linear"
    FIBONACCI = "fibonacci"


@dataclass
class RetryConfig:
    """Configuration for retry behavior"""
    max_retries: int = 3
    initial_delay: float = 1.0
    max_delay: float = 60.0
    backoff_factor: float = 2.0
    jitter: bool = True
    strategy: RetryStrategy = RetryStrategy.EXPONENTIAL
    
    # Error-specific configurations
    error_configs: Dict[ErrorType, 'RetryConfig'] = field(default_factory=dict)
    
    def get_config_for_error(self, error_type: ErrorType) -> 'RetryConfig':
        """Get retry config for specific error type"""
        return self.error_configs.get(error_type, self)


class SyncError(Exception):
    """Base class for sync errors"""
    def __init__(self, message: str, error_type: ErrorType = ErrorType.UNKNOWN, 
                 retryable: bool = True, original_error: Exception = None):
        super().__init__(message)
        self.error_type = error_type
        self.retryable = retryable
        self.original_error = original_error
        self.timestamp = time.time()


class NetworkError(SyncError):
    """Network-related errors"""
    def __init__(self, message: str, original_error: Exception = None):
        super().__init__(message, ErrorType.NETWORK, retryable=True, original_error=original_error)


class PermissionError(SyncError):
    """Permission-related errors"""
    def __init__(self, message: str, original_error: Exception = None):
        super().__init__(message, ErrorType.PERMISSION, retryable=False, original_error=original_error)


class DiskFullError(SyncError):
    """Disk full errors"""
    def __init__(self, message: str, original_error: Exception = None):
        super().__init__(message, ErrorType.DISK_FULL, retryable=False, original_error=original_error)


class FileLockError(SyncError):
    """File locked errors"""
    def __init__(self, message: str, original_error: Exception = None):
        super().__init__(message, ErrorType.FILE_LOCKED, retryable=True, original_error=original_error)


class TimeoutError(SyncError):
    """Timeout errors"""
    def __init__(self, message: str, original_error: Exception = None):
        super().__init__(message, ErrorType.TIMEOUT, retryable=True, original_error=original_error)


class CorruptionError(SyncError):
    """Data corruption errors"""
    def __init__(self, message: str, original_error: Exception = None):
        super().__init__(message, ErrorType.CORRUPTION, retryable=True, original_error=original_error)


@dataclass
class RetryAttempt:
    """Information about a retry attempt"""
    attempt_number: int
    delay: float
    error: Exception
    timestamp: float
    
    @property
    def is_final(self) -> bool:
        """Whether this was the final attempt"""
        return self.attempt_number >= 0  # Will be set by RetryManager


class RetryManager:
    """Manages retry logic with configurable strategies"""
    
    def __init__(self, config: RetryConfig = None):
        self.config = config or RetryConfig()
        self.logger = logging.getLogger(__name__)
        self._attempt_history: List[RetryAttempt] = []
        self._error_patterns = self._init_error_patterns()
    
    def _init_error_patterns(self) -> Dict[ErrorType, List[str]]:
        """Initialize error message patterns for classification"""
        return {
            ErrorType.NETWORK: [
                "connection refused", "connection timeout", "network is unreachable",
                "temporary failure", "name resolution failed", "host is down",
                "connection reset", "broken pipe", "network unreachable"
            ],
            ErrorType.PERMISSION: [
                "permission denied", "access denied", "operation not permitted",
                "insufficient privileges", "authorization failed", "forbidden"
            ],
            ErrorType.DISK_FULL: [
                "no space left on device", "disk full", "quota exceeded",
                "file system full", "insufficient disk space"
            ],
            ErrorType.FILE_LOCKED: [
                "file is locked", "resource busy", "file in use",
                "sharing violation", "lock held by another process"
            ],
            ErrorType.TIMEOUT: [
                "timeout", "operation timed out", "deadline exceeded",
                "connection timed out", "read timeout", "write timeout"
            ],
            ErrorType.CORRUPTION: [
                "checksum mismatch", "corrupt", "invalid data", "crc error",
                "data integrity error", "verification failed"
            ]
        }
    
    def classify_error(self, error: Exception) -> ErrorType:
        """Classify an error based on its message"""
        if isinstance(error, SyncError):
            return error.error_type
        
        error_message = str(error).lower()
        
        # Check each error type pattern
        for error_type, patterns in self._error_patterns.items():
            if any(pattern in error_message for pattern in patterns):
                return error_type
        
        return ErrorType.UNKNOWN
    
    def is_retryable(self, error: Exception) -> bool:
        """Determine if an error is retryable"""
        if isinstance(error, SyncError):
            return error.retryable
        
        error_type = self.classify_error(error)
        
        # Non-retryable error types
        non_retryable = {ErrorType.PERMISSION, ErrorType.DISK_FULL}
        
        return error_type not in non_retryable
    
    def calculate_delay(self, attempt: int, error_type: ErrorType = None) -> float:
        """Calculate delay for retry attempt"""
        config = self.config
        if error_type:
            config = self.config.get_config_for_error(error_type)
        
        if config.strategy == RetryStrategy.FIXED:
            delay = config.initial_delay
        elif config.strategy == RetryStrategy.LINEAR:
            delay = config.initial_delay * attempt
        elif config.strategy == RetryStrategy.EXPONENTIAL:
            delay = config.initial_delay * (config.backoff_factor ** (attempt - 1))
        elif config.strategy == RetryStrategy.FIBONACCI:
            delay = config.initial_delay * self._fibonacci(attempt)
        else:
            delay = config.initial_delay
        
        # Apply maximum delay limit
        delay = min(delay, config.max_delay)
        
        # Add jitter to prevent thundering herd
        if config.jitter:
            delay *= (0.5 + random.random())
        
        return delay
    
    def _fibonacci(self, n: int) -> float:
        """Calculate Fibonacci number for delay calculation"""
        if n <= 1:
            return 1.0
        
        a, b = 1.0, 1.0
        for _ in range(2, n + 1):
            a, b = b, a + b
        return b
    
    def execute_with_retry(self, func: Callable, *args, **kwargs) -> Any:
        """Execute a function with retry logic"""
        self._attempt_history.clear()
        
        last_error = None
        
        for attempt in range(1, self.config.max_retries + 1):
            try:
                # Execute the function
                result = func(*args, **kwargs)
                
                # Log success if this wasn't the first attempt
                if attempt > 1:
                    self.logger.info(f"Function succeeded on attempt {attempt}")
                
                return result
            
            except Exception as error:
                last_error = error
                error_type = self.classify_error(error)
                
                # Create retry attempt record
                retry_attempt = RetryAttempt(
                    attempt_number=attempt,
                    delay=0.0,
                    error=error,
                    timestamp=time.time()
                )
                
                # Check if error is retryable
                if not self.is_retryable(error):
                    self.logger.error(f"Non-retryable error: {error}")
                    retry_attempt.delay = 0.0
                    self._attempt_history.append(retry_attempt)
                    break
                
                # Check if we have more attempts
                if attempt >= self.config.max_retries:
                    self.logger.error(f"Max retries ({self.config.max_retries}) exceeded")
                    break
                
                # Calculate delay
                delay = self.calculate_delay(attempt, error_type)
                retry_attempt.delay = delay
                self._attempt_history.append(retry_attempt)
                
                self.logger.warning(
                    f"Attempt {attempt} failed ({error_type.value}): {error}. "
                    f"Retrying in {delay:.2f} seconds..."
                )
                
                # Wait before retrying
                time.sleep(delay)
        
        # All attempts failed
        self.logger.error(f"All {self.config.max_retries} attempts failed")
        
        # Raise the last error, wrapped in SyncError if needed
        if isinstance(last_error, SyncError):
            raise last_error
        else:
            error_type = self.classify_error(last_error)
            raise SyncError(
                f"Operation failed after {self.config.max_retries} attempts: {last_error}",
                error_type=error_type,
                retryable=False,
                original_error=last_error
            )
    
    def get_attempt_history(self) -> List[RetryAttempt]:
        """Get history of retry attempts"""
        return self._attempt_history.copy()
    
    def reset_history(self):
        """Reset attempt history"""
        self._attempt_history.clear()
    
    def create_error_specific_config(self, error_type: ErrorType, 
                                    **config_overrides) -> RetryConfig:
        """Create retry config for specific error type"""
        base_config = RetryConfig(
            max_retries=self.config.max_retries,
            initial_delay=self.config.initial_delay,
            max_delay=self.config.max_delay,
            backoff_factor=self.config.backoff_factor,
            jitter=self.config.jitter,
            strategy=self.config.strategy
        )
        
        # Apply overrides
        for key, value in config_overrides.items():
            if hasattr(base_config, key):
                setattr(base_config, key, value)
        
        return base_config
    
    def configure_error_handling(self):
        """Configure error-specific retry behavior"""
        # Network errors: More aggressive retries
        self.config.error_configs[ErrorType.NETWORK] = self.create_error_specific_config(
            ErrorType.NETWORK,
            max_retries=5,
            initial_delay=2.0,
            max_delay=30.0,
            strategy=RetryStrategy.EXPONENTIAL
        )
        
        # File locked errors: Quick retries
        self.config.error_configs[ErrorType.FILE_LOCKED] = self.create_error_specific_config(
            ErrorType.FILE_LOCKED,
            max_retries=10,
            initial_delay=0.5,
            max_delay=5.0,
            strategy=RetryStrategy.LINEAR
        )
        
        # Timeout errors: Slower retries
        self.config.error_configs[ErrorType.TIMEOUT] = self.create_error_specific_config(
            ErrorType.TIMEOUT,
            max_retries=3,
            initial_delay=5.0,
            max_delay=60.0,
            strategy=RetryStrategy.EXPONENTIAL
        )
        
        # Corruption errors: Fewer retries with verification
        self.config.error_configs[ErrorType.CORRUPTION] = self.create_error_specific_config(
            ErrorType.CORRUPTION,
            max_retries=2,
            initial_delay=1.0,
            max_delay=10.0,
            strategy=RetryStrategy.FIXED
        )
    
    def get_retry_stats(self) -> Dict[str, Any]:
        """Get statistics about retry attempts"""
        if not self._attempt_history:
            return {"total_attempts": 0, "success": True}
        
        error_types = {}
        total_delay = 0.0
        
        for attempt in self._attempt_history:
            error_type = self.classify_error(attempt.error)
            error_types[error_type.value] = error_types.get(error_type.value, 0) + 1
            total_delay += attempt.delay
        
        return {
            "total_attempts": len(self._attempt_history),
            "success": False,  # If we have history, it means we failed
            "total_delay": total_delay,
            "error_types": error_types,
            "final_error": str(self._attempt_history[-1].error) if self._attempt_history else None
        }


def with_retry(config: RetryConfig = None):
    """Decorator for automatic retry functionality"""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            retry_manager = RetryManager(config)
            return retry_manager.execute_with_retry(func, *args, **kwargs)
        return wrapper
    return decorator


# Convenience decorators for common retry patterns
def retry_network_errors(max_retries: int = 5, initial_delay: float = 2.0):
    """Decorator for network error retries"""
    config = RetryConfig(
        max_retries=max_retries,
        initial_delay=initial_delay,
        max_delay=30.0,
        strategy=RetryStrategy.EXPONENTIAL
    )
    return with_retry(config)


def retry_file_locked(max_retries: int = 10, initial_delay: float = 0.5):
    """Decorator for file lock retries"""
    config = RetryConfig(
        max_retries=max_retries,
        initial_delay=initial_delay,
        max_delay=5.0,
        strategy=RetryStrategy.LINEAR
    )
    return with_retry(config)


def retry_with_backoff(max_retries: int = 3, initial_delay: float = 1.0, 
                      backoff_factor: float = 2.0):
    """Decorator for exponential backoff retries"""
    config = RetryConfig(
        max_retries=max_retries,
        initial_delay=initial_delay,
        backoff_factor=backoff_factor,
        strategy=RetryStrategy.EXPONENTIAL
    )
    return with_retry(config) 