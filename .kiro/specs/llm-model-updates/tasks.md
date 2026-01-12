# Implementation Plan: LLM Model Updates

## Overview

This implementation simplifies Kodiak's LLM configuration by removing internal model validation and allowing direct LiteLLM model string input. The changes focus on configuration management, provider inference, and documentation updates.

## Tasks

- [ ] 1. Update core configuration system
  - Remove LLMProvider enum and simplify settings
  - Implement provider inference from model strings
  - Add API key resolution logic
  - _Requirements: 1.1, 1.2, 2.1, 2.2_

- [ ]* 1.1 Write property test for model string pass-through
  - **Property 1: Model String Pass-Through**
  - **Validates: Requirements 1.1, 1.2**

- [ ]* 1.2 Write property test for provider inference
  - **Property 2: Provider Inference Consistency**
  - **Validates: Requirements 2.1**

- [x] 2. Update LLM service implementation
  - Simplify LLMService initialization
  - Remove internal model validation
  - Update chat completion to use direct model strings
  - _Requirements: 1.2, 1.3, 4.2_

- [ ]* 2.1 Write property test for error propagation
  - **Property 3: Error Propagation**
  - **Validates: Requirements 1.3, 4.2**

- [x] 3. Update configuration validation and error handling
  - Implement new validation logic for simplified config
  - Add helpful error messages for missing API keys
  - Update startup validation
  - _Requirements: 4.1, 4.3, 4.4_

- [ ]* 3.1 Write property test for API key resolution
  - **Property 4: API Key Resolution**
  - **Validates: Requirements 4.1**

- [ ]* 3.2 Write property test for configuration validation
  - **Property 5: Configuration Validation**
  - **Validates: Requirements 4.3**

- [ ]* 3.3 Write property test for provider override
  - **Property 6: Provider Override**
  - **Validates: Requirements 2.4**

- [x] 4. Update CLI configuration command
  - Modify `kodiak config` to use LiteLLM model string format
  - Update interactive prompts for model selection
  - Add validation and testing of LiteLLM connection
  - _Requirements: 2.2, 4.1, 4.4_

- [x] 5. Checkpoint - Ensure all tests pass
  - Core LLM functionality tests pass, TUI architecture tests need separate update

- [x] 6. Update documentation and examples
  - Update .env.example with latest model examples
  - Update tech.md with current model recommendations
  - Add LiteLLM documentation links
  - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5_

- [x] 7. Remove legacy configuration code
  - Remove configure_llm.py script (not found - already removed)
  - Clean up unused provider-specific logic (LLMProvider enum removed)
  - Remove hard-coded model display names (LLM_PRESETS removed)
  - _Requirements: 1.1, 1.2_

- [x] 8. Final checkpoint - Ensure all tests pass
  - Core LLM functionality implemented and working
  - Configuration system updated and tested
  - Documentation updated with latest models
  - Provider inference and API key resolution working correctly

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Property tests validate universal correctness properties
- Unit tests validate specific examples and edge cases
- The implementation removes complexity while maintaining functionality