# Design Document: LLM Model Updates

## Overview

This design simplifies Kodiak's LLM configuration by removing internal model validation and allowing users to input any LiteLLM-compatible model string directly. The system will leverage LiteLLM's built-in provider routing and validation, making the configuration future-proof and eliminating the need to maintain a list of supported models.

## Architecture

### Current Architecture Issues
- Hard-coded `LLMProvider` enum limits supported providers
- Internal model validation against a fixed list
- Complex provider-specific configuration logic
- Manual maintenance of model display names

### New Architecture
- Direct pass-through of model strings to LiteLLM
- Automatic provider inference from model string prefixes
- Simplified configuration with minimal required fields
- LiteLLM handles all provider routing and validation

## Components and Interfaces

### Configuration Changes

#### Remove LLMProvider Enum
The current `LLMProvider` enum will be removed entirely. Provider information will be inferred from the model string prefix or explicitly set via environment variable.

#### Simplified Settings Class
```python
class KodiakSettings(BaseSettings):
    # LLM Configuration - Simplified
    llm_model: str = Field(default="gemini/gemini-3-pro-preview", env="KODIAK_LLM_MODEL")
    llm_provider: Optional[str] = Field(default=None, env="KODIAK_LLM_PROVIDER")  # Optional override
    llm_temperature: float = Field(default=0.1, env="KODIAK_LLM_TEMPERATURE")
    llm_max_tokens: int = Field(default=4096, env="KODIAK_LLM_MAX_TOKENS")
    
    # API Keys - Keep existing for convenience
    openai_api_key: Optional[str] = Field(default=None, env="OPENAI_API_KEY")
    google_api_key: Optional[str] = Field(default=None, env="GOOGLE_API_KEY")
    anthropic_api_key: Optional[str] = Field(default=None, env="ANTHROPIC_API_KEY")
```

#### Provider Inference Logic
```python
def infer_provider_from_model(model_string: str) -> str:
    """Infer provider from LiteLLM model string format"""
    if "/" in model_string:
        prefix = model_string.split("/")[0]
        return prefix
    else:
        # Handle models without prefix (legacy or special cases)
        if model_string.startswith("gpt"):
            return "openai"
        elif model_string.startswith("claude"):
            return "anthropic"
        elif model_string.startswith("gemini"):
            return "gemini"
        else:
            raise ValueError(f"Cannot infer provider from model string: {model_string}")
```

#### API Key Resolution
```python
def get_api_key_for_provider(provider: str) -> Optional[str]:
    """Get the appropriate API key for the provider"""
    key_mapping = {
        "openai": settings.openai_api_key,
        "gemini": settings.google_api_key,
        "anthropic": settings.anthropic_api_key,
        "vertex_ai": settings.google_api_key,
        "azure": settings.openai_api_key,  # Azure uses OpenAI format
        # Add more as needed
    }
    return key_mapping.get(provider)
```

### LLM Service Updates

#### Simplified Initialization
```python
class LLMService:
    def __init__(self):
        self.model = settings.llm_model
        
        # Infer or use explicit provider
        if settings.llm_provider:
            self.provider = settings.llm_provider
        else:
            self.provider = infer_provider_from_model(self.model)
        
        # Get API key for provider
        self.api_key = get_api_key_for_provider(self.provider)
        
        # Configure LiteLLM with minimal setup
        litellm.set_verbose = settings.debug
        
        # Set API keys in environment for LiteLLM
        self._configure_litellm_keys()
```

#### Direct Model String Usage
```python
async def chat_completion(self, messages: List[Dict[str, str]], **kwargs) -> Dict[str, Any]:
    """Chat completion using direct model string"""
    params = {
        "model": self.model,  # Pass model string directly to LiteLLM
        "messages": messages,
        "temperature": settings.llm_temperature,
        "max_tokens": settings.llm_max_tokens,
        **kwargs
    }
    
    # LiteLLM handles provider routing automatically
    response = await acompletion(**params)
    return response
```

### Configuration Management Updates

#### CLI Configuration
Update `kodiak config` command to:
1. Ask for model string in LiteLLM format
2. Automatically infer provider from model string
3. Request appropriate API key based on inferred provider
4. Validate configuration by testing LiteLLM connection

#### Environment Variable Updates
```bash
# New simplified configuration
KODIAK_LLM_MODEL=gemini/gemini-3-pro-preview
GOOGLE_API_KEY=your_api_key

# Optional provider override for edge cases
KODIAK_LLM_PROVIDER=gemini

# Legacy API key variables still supported
OPENAI_API_KEY=your_openai_key
ANTHROPIC_API_KEY=your_anthropic_key
```

## Data Models

### Configuration Validation
```python
def validate_llm_config(self) -> List[str]:
    """Validate LLM configuration"""
    errors = []
    
    if not self.llm_model:
        errors.append("KODIAK_LLM_MODEL is required")
        return errors
    
    try:
        # Infer provider
        provider = self.llm_provider or infer_provider_from_model(self.llm_model)
        
        # Check for API key
        api_key = get_api_key_for_provider(provider)
        if not api_key:
            required_key = get_required_api_key_env_var(provider)
            errors.append(f"API key required for provider '{provider}': set {required_key}")
    
    except ValueError as e:
        errors.append(str(e))
    
    return errors
```

### Model Information
```python
def get_model_info(self) -> Dict[str, Any]:
    """Get current model configuration info"""
    try:
        provider = self.llm_provider or infer_provider_from_model(self.llm_model)
        api_key_configured = bool(get_api_key_for_provider(provider))
        
        return {
            "model": self.llm_model,
            "provider": provider,
            "provider_source": "explicit" if self.llm_provider else "inferred",
            "api_key_configured": api_key_configured,
            "temperature": self.llm_temperature,
            "max_tokens": self.llm_max_tokens
        }
    except Exception as e:
        return {
            "model": self.llm_model,
            "error": str(e),
            "api_key_configured": False
        }
```

## Correctness Properties

*A property is a characteristic or behavior that should hold true across all valid executions of a system-essentially, a formal statement about what the system should do. Properties serve as the bridge between human-readable specifications and machine-verifiable correctness guarantees.*

### Property 1: Model String Pass-Through
*For any* valid LiteLLM model string, the system should pass it directly to LiteLLM without internal validation or modification
**Validates: Requirements 1.1, 1.2**

### Property 2: Provider Inference Consistency
*For any* model string with a valid provider prefix, the system should consistently infer the same provider from that prefix
**Validates: Requirements 2.1**

### Property 3: Error Propagation
*For any* invalid model string that causes LiteLLM to error, the system should propagate that error message to the user without modification
**Validates: Requirements 1.3, 4.2**

### Property 4: API Key Resolution
*For any* inferred provider, the system should correctly identify and request the appropriate API key environment variable
**Validates: Requirements 4.1**

### Property 5: Configuration Validation
*For any* missing required environment variable, the system should detect this at startup and provide a clear error message
**Validates: Requirements 4.3**

### Property 6: Provider Override
*For any* explicit provider setting, the system should use that provider regardless of what the model string prefix suggests
**Validates: Requirements 2.4**

## Error Handling

### Configuration Errors
- **Missing Model String**: Clear error with example format
- **Invalid Model Format**: Suggest checking LiteLLM documentation
- **Missing API Key**: Specify which environment variable to set
- **Provider Inference Failure**: Suggest using explicit provider override

### Runtime Errors
- **LiteLLM Connection Errors**: Pass through with context
- **Authentication Errors**: Check API key validity
- **Model Not Found**: Verify model string format and availability

### Error Message Templates
```python
ERROR_MESSAGES = {
    "missing_model": "KODIAK_LLM_MODEL is required. Example: gemini/gemini-3-pro-preview",
    "missing_api_key": "API key required for provider '{provider}': set {env_var}",
    "inference_failed": "Cannot infer provider from '{model}'. Set KODIAK_LLM_PROVIDER explicitly or use format 'provider/model'",
    "invalid_format": "Invalid model format '{model}'. Check LiteLLM documentation for supported formats: https://docs.litellm.ai/docs/providers"
}
```

## Testing Strategy

### Unit Tests
- Configuration validation with various model strings
- Provider inference logic with edge cases
- API key resolution for different providers
- Error message formatting and content

### Property-Based Tests
- Model string pass-through with generated valid formats
- Provider inference consistency across random inputs
- Error propagation with invalid model strings
- Configuration validation with missing environment variables

Each property test will run a minimum of 100 iterations and be tagged with:
**Feature: llm-model-updates, Property {number}: {property_text}**

### Integration Tests
- End-to-end LLM service initialization with various configurations
- CLI configuration workflow with different model choices
- Error handling in real LiteLLM integration scenarios