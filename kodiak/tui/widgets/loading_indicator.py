"""
Loading Indicator Widget

Provides visual feedback for async operations to ensure non-blocking UI.
"""

import asyncio
from typing import Optional
from textual.widget import Widget
from textual.widgets import Static
from textual.containers import Container, Horizontal
from textual.app import ComposeResult
from textual.reactive import reactive


class LoadingIndicator(Widget):
    """
    A loading indicator widget that shows animated progress
    """
    
    DEFAULT_CLASS = "loading-indicator"
    
    # Reactive properties
    is_loading: reactive[bool] = reactive(False)
    message: reactive[str] = reactive("Loading...")
    
    def __init__(
        self,
        message: str = "Loading...",
        show_spinner: bool = True,
        **kwargs
    ):
        super().__init__(**kwargs)
        self.message = message
        self.show_spinner = show_spinner
        self._spinner_task: Optional[asyncio.Task] = None
        self._spinner_chars = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
        self._spinner_index = 0
    
    def compose(self) -> ComposeResult:
        """Compose the loading indicator"""
        with Container(id="loading-container"):
            with Horizontal(id="loading-content"):
                yield Static("", id="spinner")
                yield Static(self.message, id="loading-message")
    
    def on_mount(self) -> None:
        """Start the loading animation when mounted"""
        if self.is_loading and self.show_spinner:
            self._start_spinner()
    
    def watch_is_loading(self, is_loading: bool) -> None:
        """React to loading state changes"""
        if is_loading and self.show_spinner:
            self._start_spinner()
        else:
            self._stop_spinner()
        
        # Update visibility
        self.display = is_loading
    
    def watch_message(self, message: str) -> None:
        """React to message changes"""
        message_widget = self.query_one("#loading-message", Static)
        message_widget.update(message)
    
    def _start_spinner(self) -> None:
        """Start the spinner animation"""
        if self._spinner_task is None or self._spinner_task.done():
            self._spinner_task = asyncio.create_task(self._animate_spinner())
    
    def _stop_spinner(self) -> None:
        """Stop the spinner animation"""
        if self._spinner_task and not self._spinner_task.done():
            self._spinner_task.cancel()
            self._spinner_task = None
        
        # Clear spinner
        try:
            spinner_widget = self.query_one("#spinner", Static)
            spinner_widget.update("")
        except:
            pass
    
    async def _animate_spinner(self) -> None:
        """Animate the spinner"""
        try:
            while True:
                spinner_widget = self.query_one("#spinner", Static)
                spinner_widget.update(self._spinner_chars[self._spinner_index])
                self._spinner_index = (self._spinner_index + 1) % len(self._spinner_chars)
                await asyncio.sleep(0.1)
        except asyncio.CancelledError:
            pass
        except Exception:
            # Ignore errors during animation
            pass
    
    def start_loading(self, message: str = None) -> None:
        """Start loading with optional message"""
        if message:
            self.message = message
        self.is_loading = True
    
    def stop_loading(self) -> None:
        """Stop loading"""
        self.is_loading = False
    
    def update_message(self, message: str) -> None:
        """Update the loading message"""
        self.message = message


class ProgressIndicator(Widget):
    """
    A progress indicator for operations with known progress
    """
    
    DEFAULT_CLASS = "progress-indicator"
    
    # Reactive properties
    progress: reactive[float] = reactive(0.0)  # 0.0 to 1.0
    message: reactive[str] = reactive("Processing...")
    
    def __init__(
        self,
        message: str = "Processing...",
        width: int = 40,
        **kwargs
    ):
        super().__init__(**kwargs)
        self.message = message
        self.progress_width = width
    
    def compose(self) -> ComposeResult:
        """Compose the progress indicator"""
        with Container(id="progress-container"):
            yield Static(self.message, id="progress-message")
            yield Static("", id="progress-bar")
            yield Static("0%", id="progress-percentage")
    
    def watch_progress(self, progress: float) -> None:
        """React to progress changes"""
        # Clamp progress between 0 and 1
        progress = max(0.0, min(1.0, progress))
        
        # Update progress bar
        filled_width = int(progress * self.progress_width)
        empty_width = self.progress_width - filled_width
        
        bar = "█" * filled_width + "░" * empty_width
        
        try:
            bar_widget = self.query_one("#progress-bar", Static)
            bar_widget.update(f"[{bar}]")
            
            percentage_widget = self.query_one("#progress-percentage", Static)
            percentage_widget.update(f"{int(progress * 100)}%")
        except:
            pass
    
    def watch_message(self, message: str) -> None:
        """React to message changes"""
        try:
            message_widget = self.query_one("#progress-message", Static)
            message_widget.update(message)
        except:
            pass
    
    def update_progress(self, progress: float, message: str = None) -> None:
        """Update progress and optionally message"""
        self.progress = progress
        if message:
            self.message = message
    
    def reset(self) -> None:
        """Reset progress to 0"""
        self.progress = 0.0


class AsyncOperationWidget(Widget):
    """
    Widget that manages async operations with loading indicators
    """
    
    DEFAULT_CLASS = "async-operation"
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.loading_indicator = LoadingIndicator()
        self._current_operation: Optional[asyncio.Task] = None
    
    def compose(self) -> ComposeResult:
        """Compose the async operation widget"""
        yield self.loading_indicator
    
    async def run_async_operation(
        self,
        operation_func,
        loading_message: str = "Processing...",
        success_message: str = "Operation completed",
        *args,
        **kwargs
    ):
        """
        Run an async operation with loading indicator
        
        Args:
            operation_func: The async function to execute
            loading_message: Message to show while loading
            success_message: Message to show on success
            *args, **kwargs: Arguments to pass to operation_func
        
        Returns:
            The result of the operation or None if failed
        """
        try:
            # Start loading
            self.loading_indicator.start_loading(loading_message)
            
            # Run the operation
            result = await operation_func(*args, **kwargs)
            
            # Stop loading
            self.loading_indicator.stop_loading()
            
            # Show success message briefly
            if success_message:
                self.app.notify(success_message, severity="information", timeout=3)
            
            return result
            
        except Exception as e:
            # Stop loading
            self.loading_indicator.stop_loading()
            
            # Show error message
            self.app.notify(f"Operation failed: {str(e)}", severity="error", timeout=5)
            
            return None
    
    def cancel_operation(self) -> None:
        """Cancel the current operation"""
        if self._current_operation and not self._current_operation.done():
            self._current_operation.cancel()
        
        self.loading_indicator.stop_loading()