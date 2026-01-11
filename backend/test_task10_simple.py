#!/usr/bin/env python3
"""
Simple test for Task 10: Configuration Validation
Tests the core functionality without complex mocking.
"""

import sys
import os

# Add the backend directory to the Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__)))

def test_configuration_imports():
    """Test that all configuration modules can be imported"""
    print("Testing configuration imports...")
    
    try:
        from kodiak.core.config import (
            settings, validate_startup_config, KodiakSettings,
            get_available_models, configure_for_gemini, configure_for_openai, configure_for_claude,
            get_configuration_troubleshooting_guide, diagnose_configuration_issues
        )
        print("✓ All configuration imports successful")
        return True
    except Exception as e:
        print(f"❌ Configuration import failed: {e}")
        return False


def test_configuration_helpers():
    """Test configuration helper functions"""
    print("Testing configuration helpers...")
    
    try:
        from kodiak.core.config import (
            get_available_models, configure_for_gemini, configure_for_openai, configure_for_claude,
            get_configuration_troubleshooting_guide, diagnose_configuration_issues
        )
        
        # Test model presets
        models = get_available_models()
        if not models or len(models) == 0:
            print("❌ No model presets available")
            return False
        print(f"✓ Found {len(models)} model presets")
        
        # Test configuration helpers
        gemini_config = configure_for_gemini("test_key")
        openai_config = configure_for_openai("test_key")
        claude_config = configure_for_claude("test_key")
        
        if not all([gemini_config, openai_config, claude_config]):
            print("❌ Configuration helpers not working")
            return False
        print("✓ Configuration helpers working")
        
        # Test troubleshooting guide
        guide = get_configuration_troubleshooting_guide()
        if not guide or "common_issues" not in guide:
            print("❌ Troubleshooting guide not available")
            return False
        print("✓ Troubleshooting guide available")
        
        # Test diagnosis
        diagnosis = diagnose_configuration_issues()
        if not diagnosis or "has_issues" not in diagnosis:
            print("❌ Configuration diagnosis not working")
            return False
        print("✓ Configuration diagnosis working")
        
        return True
        
    except Exception as e:
        print(f"❌ Configuration helpers test failed: {e}")
        return False


def test_settings_validation():
    """Test settings validation functionality"""
    print("Testing settings validation...")
    
    try:
        from kodiak.core.config import settings
        
        # Test validation method exists
        if not hasattr(settings, 'validate_required_config'):
            print("❌ Settings validation method not found")
            return False
        
        # Test validation runs without error
        missing = settings.validate_required_config()
        print(f"✓ Settings validation completed, missing items: {len(missing)}")
        
        # Test other settings methods
        if not hasattr(settings, 'get_llm_config'):
            print("❌ LLM config method not found")
            return False
        
        llm_config = settings.get_llm_config()
        print("✓ LLM config method working")
        
        if not hasattr(settings, 'get_model_display_name'):
            print("❌ Model display name method not found")
            return False
        
        display_name = settings.get_model_display_name()
        print(f"✓ Model display name: {display_name}")
        
        return True
        
    except Exception as e:
        print(f"❌ Settings validation test failed: {e}")
        return False


def test_error_handling_integration():
    """Test error handling integration with configuration"""
    print("Testing error handling integration...")
    
    try:
        from kodiak.core.error_handling import ConfigurationError, ErrorHandler
        
        # Test creating configuration error
        config_error = ConfigurationError(
            message="Test configuration error",
            config_key="test_key"
        )
        
        # Test error to dict
        error_dict = config_error.to_dict()
        if not error_dict or "error" not in error_dict:
            print("❌ Configuration error to_dict not working")
            return False
        
        print("✓ Configuration error handling working")
        return True
        
    except Exception as e:
        print(f"❌ Error handling integration test failed: {e}")
        return False


def main():
    """Run all simple configuration tests"""
    print("=" * 60)
    print("Simple Test: Task 10 Configuration Validation")
    print("=" * 60)
    
    tests = [
        test_configuration_imports,
        test_configuration_helpers,
        test_settings_validation,
        test_error_handling_integration
    ]
    
    passed = 0
    total = len(tests)
    
    for test in tests:
        try:
            if test():
                passed += 1
            print()  # Add spacing between tests
        except Exception as e:
            print(f"❌ Test {test.__name__} failed with exception: {e}")
            print()
    
    print("=" * 60)
    print(f"Results: {passed}/{total} tests passed")
    
    if passed == total:
        print("✅ All configuration validation tests passed!")
        print("Task 10 implementation appears to be working correctly.")
    else:
        print("❌ Some configuration validation tests failed.")
        print("Task 10 implementation needs review.")
    
    print("=" * 60)
    return passed == total


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)