"""Custom exceptions for the StockPredictor backend."""


class StockPredictorError(Exception):
    """Base exception for the application."""
    def __init__(self, message: str, code: int = 500):
        self.message = message
        self.code = code
        super().__init__(message)


class DataSourceError(StockPredictorError):
    """Raised when all data sources fail."""

    def __init__(self, message: str = "All data sources are unavailable"):
        super().__init__(message, code=503)


class StockNotFoundError(StockPredictorError):
    """Raised when a stock code is not found."""

    def __init__(self, code: str):
        super().__init__(f"Stock '{code}' not found", code=404)


class PredictionNotReadyError(StockPredictorError):
    """Raised when prediction is not yet available."""

    def __init__(self, code: str):
        super().__init__(f"Prediction for '{code}' is not yet available", code=404)


class RateLimitExceededError(StockPredictorError):
    """Raised when API rate limit is exceeded."""

    def __init__(self):
        super().__init__("Request rate limit exceeded. Please try again later.", code=429)


class ModelLoadError(StockPredictorError):
    """Raised when ML model fails to load."""

    def __init__(self, model_name: str):
        super().__init__(f"Failed to load model '{model_name}'", code=500)


class InvalidParameterError(StockPredictorError):
    """Raised when request parameters are invalid."""

    def __init__(self, detail: str):
        super().__init__(f"Invalid parameter: {detail}", code=400)
