# Requirements Document

## Introduction

Kodiak's LLM configuration should be simplified to allow users to directly input any LiteLLM-compatible model string. This approach leverages LiteLLM's built-in provider routing and future-proofs the configuration without requiring Kodiak to maintain a list of supported models. The documentation will be updated with current recommended models (Gemini 3, GPT-5, Claude 4.5) as examples.

## Glossary

- **LLM**: Large Language Model - AI models used for natural language processing and generation
- **Kodiak**: The AI-powered penetration testing suite
- **LiteLLM**: The multi-provider LLM integration library used by Kodiak that handles provider routing
- **Model_String**: LiteLLM format model identifier (e.g., `gemini/gemini-3-pro-preview`)
- **API_Key**: Authentication credential for the LLM provider

## Requirements

### Requirement 1: Flexible Model Configuration

**User Story:** As a security professional, I want to input any LiteLLM-compatible model string, so that I can use any current or future model without waiting for Kodiak updates.

#### Acceptance Criteria

1. THE System SHALL accept any valid LiteLLM model string format via `KODIAK_LLM_MODEL` environment variable
2. THE System SHALL pass the model string directly to LiteLLM without internal validation against a model list
3. WHEN an invalid model string is provided, THE System SHALL display the error from LiteLLM
4. THE System SHALL support all LiteLLM provider prefixes (gemini/, openai/, anthropic/, ollama/, etc.)

### Requirement 2: Simplified Provider Configuration

**User Story:** As a system administrator, I want simplified provider configuration, so that I can quickly set up LLM access with minimal configuration.

#### Acceptance Criteria

1. THE System SHALL infer the provider from the model string prefix when `KODIAK_LLM_PROVIDER` is not set
2. THE System SHALL require only the model string and appropriate API key for basic configuration
3. WHEN the provider cannot be inferred, THE System SHALL display a helpful error message
4. THE System SHALL support explicit provider override via `KODIAK_LLM_PROVIDER` for edge cases

### Requirement 3: Updated Documentation with Current Models

**User Story:** As a developer, I want updated documentation with current model examples, so that I can quickly configure Kodiak with recommended models.

#### Acceptance Criteria

1. THE System documentation SHALL include examples for Gemini 3 models (gemini/gemini-3-pro-preview, gemini/gemini-3-flash-preview)
2. THE System documentation SHALL include examples for latest OpenAI models
3. THE System documentation SHALL include examples for Claude 4.5 models
4. THE System documentation SHALL link to LiteLLM's model documentation for the full list of supported models
5. THE System documentation SHALL explain the model string format clearly

### Requirement 4: Configuration Validation and Error Handling

**User Story:** As a user, I want clear error messages when configuration is incorrect, so that I can quickly diagnose and fix issues.

#### Acceptance Criteria

1. WHEN the API key is missing for the inferred provider, THE System SHALL display which API key environment variable is needed
2. WHEN LiteLLM returns a model error, THE System SHALL display the error clearly to the user
3. THE System SHALL validate that required environment variables are set at startup
4. IF the model string format is unrecognized, THEN THE System SHALL suggest checking LiteLLM documentation

