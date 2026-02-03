"""
FocusTrack - Desktop Core Module
Cross-platform window detection and input tracking for Windows & macOS.

NOTE: On macOS, pynput can cause crashes with Tkinter. 
This version uses a safer approach with optional input tracking.
"""

import time
import platform
import threading
from datetime import datetime, timedelta
from typing import Dict, Optional, Callable

# Flag to enable/disable input monitoring (may crash on macOS)
ENABLE_INPUT_MONITORING = False  # Set to True if you have proper permissions

# ============================================================================
# CROSS-PLATFORM WINDOW DETECTION
# ============================================================================

def get_active_window_info() -> Dict[str, str]:
    """
    Get the currently active window's app name and title.
    
    Returns:
        dict: {'app_name': str, 'title': str}
    """
    system = platform.system()
    
    if system == "Darwin":  # macOS
        return _get_macos_active_window()
    elif system == "Windows":
        return _get_windows_active_window()
    else:
        return {"app_name": "Unknown", "title": "Unsupported OS"}


def _get_macos_active_window() -> Dict[str, str]:
    """
    Get active window info on macOS using Accessibility API (AXUIElement).
    This is the professional approach used by Hubstaff, Time Doctor, RescueTime.
    Requires Accessibility permissions in System Settings.
    """
    try:
        from AppKit import NSWorkspace
        from Quartz import (
            CGWindowListCopyWindowInfo,
            kCGWindowListOptionOnScreenOnly,
            kCGWindowListExcludeDesktopElements,
            kCGNullWindowID
        )
        # Import Accessibility API
        from ApplicationServices import (
            AXUIElementCreateApplication,
            AXUIElementCopyAttributeValue,
            kAXFocusedWindowAttribute,
            kAXTitleAttribute,
            kAXErrorSuccess
        )
        from Foundation import NSString
        
        # Get the frontmost application
        workspace = NSWorkspace.sharedWorkspace()
        active_app = workspace.frontmostApplication()
        app_name = active_app.localizedName() if active_app else "Unknown"
        pid = active_app.processIdentifier() if active_app else None
        
        window_title = ""
        
        if pid:
            # Method 1: Use Accessibility API (most reliable)
            try:
                app_ref = AXUIElementCreateApplication(pid)
                
                # Get the focused window
                err, focused_window = AXUIElementCopyAttributeValue(
                    app_ref, kAXFocusedWindowAttribute, None
                )
                
                if err == kAXErrorSuccess and focused_window:
                    # Get the window title
                    err, title = AXUIElementCopyAttributeValue(
                        focused_window, kAXTitleAttribute, None
                    )
                    if err == kAXErrorSuccess and title:
                        window_title = str(title)
            except Exception:
                pass  # Fall through to Quartz method
            
            # Method 2: Fallback to Quartz CGWindowList
            if not window_title:
                options = kCGWindowListOptionOnScreenOnly | kCGWindowListExcludeDesktopElements
                window_list = CGWindowListCopyWindowInfo(options, kCGNullWindowID)
                
                # Find windows belonging to the active app
                for window in window_list:
                    if window.get('kCGWindowOwnerPID') == pid:
                        layer = window.get('kCGWindowLayer', 0)
                        title = window.get('kCGWindowName', '') or ''
                        # Get normal windows (layer 0), skip menu bars
                        if title and layer == 0:
                            window_title = title
                            break
        
        # Final fallback: use app name
        if not window_title:
            window_title = app_name
        
        return {"app_name": app_name, "title": window_title}
        
    except ImportError as e:
        return {"app_name": "Error", "title": f"Missing: {e}"}
    except Exception as e:
        return {"app_name": "Error", "title": str(e)}


def _get_windows_active_window() -> Dict[str, str]:
    """Get active window info on Windows using pygetwindow and psutil."""
    try:
        import pygetwindow as gw
        import psutil
        import win32process
        import win32gui
        
        # Get the active window
        hwnd = win32gui.GetForegroundWindow()
        window_title = win32gui.GetWindowText(hwnd)
        
        # Get the process ID and then the app name
        _, pid = win32process.GetWindowThreadProcessId(hwnd)
        
        try:
            process = psutil.Process(pid)
            app_name = process.name()
            # Remove .exe extension for cleaner display
            if app_name.lower().endswith('.exe'):
                app_name = app_name[:-4]
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            app_name = "Unknown"
        
        return {"app_name": app_name, "title": window_title}
        
    except ImportError:
        return {"app_name": "Error", "title": "pygetwindow/psutil not available"}
    except Exception as e:
        return {"app_name": "Error", "title": str(e)}


# ============================================================================
# INPUT TRACKING (Simplified - no pynput on macOS to avoid crashes)
# ============================================================================

# Global counters for mouse and keyboard events
mouse_count = 0
key_count = 0

# Lock for thread-safe counter access
_counter_lock = threading.Lock()

# Listener references (to stop them later)
_mouse_listener = None
_keyboard_listener = None
_input_listeners_started = False


def _on_mouse_click(x, y, button, pressed):
    """Callback for mouse click events."""
    global mouse_count
    if pressed:
        with _counter_lock:
            mouse_count += 1


def _on_mouse_move(x, y):
    """Callback for mouse move events."""
    global mouse_count
    with _counter_lock:
        mouse_count += 1


def _on_key_press(key):
    """Callback for keyboard press events."""
    global key_count
    with _counter_lock:
        key_count += 1


def start_input_listeners():
    """Start mouse and keyboard listeners (if enabled)."""
    global _mouse_listener, _keyboard_listener, _input_listeners_started
    
    if not ENABLE_INPUT_MONITORING:
        print("[InputListeners] Disabled (set ENABLE_INPUT_MONITORING=True to enable)")
        _input_listeners_started = False
        return True
    
    if platform.system() == "Darwin":
        # On macOS, use Quartz for idle detection instead of pynput
        # This avoids Tkinter crashes and doesn't need Accessibility permissions
        print("[InputListeners] macOS detected - using Quartz idle detection (no pynput)")
        _input_listeners_started = False  # pynput not used
        return True  # Success - will use get_macos_idle_seconds() instead
    
    try:
        from pynput import mouse, keyboard
        
        # Mouse listener (clicks only, not moves - to reduce overhead)
        _mouse_listener = mouse.Listener(
            on_click=_on_mouse_click
        )
        _mouse_listener.start()
        
        # Keyboard listener
        _keyboard_listener = keyboard.Listener(
            on_press=_on_key_press
        )
        _keyboard_listener.start()
        
        _input_listeners_started = True
        print("[InputListeners] Started successfully")
        return True
        
    except ImportError:
        print("[InputListeners] pynput not installed, input tracking disabled")
        return True
    except Exception as e:
        print(f"[InputListeners] Error: {e}")
        return True  # Continue without input monitoring


def stop_input_listeners():
    """Stop mouse and keyboard listeners."""
    global _mouse_listener, _keyboard_listener, _input_listeners_started
    
    if _mouse_listener:
        try:
            _mouse_listener.stop()
        except:
            pass
        _mouse_listener = None
        
    if _keyboard_listener:
        try:
            _keyboard_listener.stop()
        except:
            pass
        _keyboard_listener = None
    
    _input_listeners_started = False
    print("[InputListeners] Stopped")


def get_and_reset_counters() -> Dict[str, int]:
    """Get current input counts and reset them to zero."""
    global mouse_count, key_count
    
    with _counter_lock:
        counts = {
            "mouse_count": mouse_count,
            "key_count": key_count
        }
        mouse_count = 0
        key_count = 0
    
    return counts


# ============================================================================
# IDLE DETECTION
# ============================================================================

def get_macos_idle_seconds() -> float:
    """
    Get the number of seconds since last user input on macOS.
    Uses Quartz CGEventSourceSecondsSinceLastEventType.
    This works without Accessibility permissions for basic idle detection.
    """
    try:
        from Quartz import (
            CGEventSourceSecondsSinceLastEventType,
            kCGEventSourceStateCombinedSessionState,
            kCGAnyInputEventType
        )
        
        # Get seconds since any input event (keyboard, mouse, etc.)
        idle_time = CGEventSourceSecondsSinceLastEventType(
            kCGEventSourceStateCombinedSessionState,
            kCGAnyInputEventType
        )
        return idle_time
        
    except ImportError:
        return 0.0  # Assume active if Quartz not available
    except Exception:
        return 0.0

# Track last activity time for idle detection
_last_activity_time = datetime.now()
IDLE_THRESHOLD_MINUTES = 5

# Track window changes as activity indicator
_last_window_info = {"app_name": "", "title": ""}


def update_activity_time():
    """Update the last activity timestamp."""
    global _last_activity_time
    _last_activity_time = datetime.now()


def check_window_changed(current_window: Dict[str, str]) -> bool:
    """Check if the window has changed (indicates activity)."""
    global _last_window_info
    
    changed = (
        current_window["app_name"] != _last_window_info["app_name"] or
        current_window["title"] != _last_window_info["title"]
    )
    
    _last_window_info = current_window.copy()
    return changed


def is_idle() -> bool:
    """
    Check if the user has been idle for more than IDLE_THRESHOLD_MINUTES.
    
    Returns:
        bool: True if idle, False otherwise
    """
    idle_threshold = timedelta(minutes=IDLE_THRESHOLD_MINUTES)
    return (datetime.now() - _last_activity_time) > idle_threshold


# ============================================================================
# MAIN MONITORING LOOP
# ============================================================================

# Control flag for the monitoring loop
tracking_active = False

# Callback for when data is collected (to be set by main.py)
on_data_collected: Optional[Callable] = None


def monitor_loop(interval_seconds: int = 5):
    """
    Main monitoring loop that runs every `interval_seconds`.
    
    Collects:
    - Active window info (app_name, title)
    - Input counts (mouse, keyboard) - if pynput is working
    - Idle status (based on window changes or input)
    
    Args:
        interval_seconds: How often to collect data (default: 5 seconds)
    """
    global tracking_active, _last_activity_time
    
    print(f"[MonitorLoop] Started (interval: {interval_seconds}s)")
    
    # Track consecutive idle intervals for idle detection
    idle_intervals = 0
    # 5 minutes = 300 seconds, at 5 second intervals = 60 intervals
    idle_threshold_intervals = (IDLE_THRESHOLD_MINUTES * 60) // interval_seconds
    
    while tracking_active:
        try:
            # Get active window info
            window_info = get_active_window_info()
            
            # Get and reset input counters
            input_counts = get_and_reset_counters()
            total_inputs = input_counts["mouse_count"] + input_counts["key_count"]
            
            # Check if window changed (fallback activity detection for macOS)
            window_changed = check_window_changed(window_info)
            
            # On macOS without pynput, use Quartz to check for recent activity
            has_recent_activity = False
            if platform.system() == "Darwin" and not _input_listeners_started:
                # Use Quartz-based idle detection
                macos_idle_secs = get_macos_idle_seconds()
                # Consider active if any input in the last interval
                has_recent_activity = macos_idle_secs < interval_seconds
            else:
                # On Windows/Linux, use pynput counters
                has_recent_activity = total_inputs > 0
            
            # Update idle tracking
            if has_recent_activity or window_changed:
                idle_intervals = 0
                update_activity_time()
            else:
                idle_intervals += 1
            
            # Check if idle (no activity for 5 minutes)
            is_user_idle = idle_intervals >= idle_threshold_intervals
            
            # Prepare log data
            log_data = {
                "timestamp": datetime.now().isoformat(),
                "app_name": window_info["app_name"],
                "window_title": window_info["title"],
                "mouse_count": input_counts["mouse_count"],
                "key_count": input_counts["key_count"],
                "is_idle": is_user_idle
            }
            
            # Print to console (for debugging)
            status = "IDLE" if is_user_idle else "ACTIVE"
            activity = "🔄" if window_changed else "  "
            print(f"[{log_data['timestamp'][:19]}] {activity} {window_info['app_name'][:20]:20} | "
                  f"{window_info['title'][:30]:30} | {status}")
            
            # Call the callback if set (for saving to database)
            if on_data_collected:
                on_data_collected(log_data)
            
        except Exception as e:
            print(f"[MonitorLoop] Error: {e}")
        
        # Wait for the next interval
        time.sleep(interval_seconds)
    
    print("[MonitorLoop] Stopped")


def start_monitoring():
    """Start the monitoring in a separate thread."""
    global tracking_active
    
    if tracking_active:
        print("[Tracking] Already running")
        return None
    
    tracking_active = True
    
    # Start input listeners (may be disabled on macOS)
    start_input_listeners()
    
    # Start monitor loop in a separate thread
    monitor_thread = threading.Thread(target=monitor_loop, daemon=True)
    monitor_thread.start()
    
    print("[Tracking] Started")
    return monitor_thread


def stop_monitoring():
    """Stop the monitoring loop and input listeners."""
    global tracking_active
    
    tracking_active = False
    stop_input_listeners()
    
    print("[Tracking] Stopped")


# ============================================================================
# TEST / DEMO MODE
# ============================================================================

if __name__ == "__main__":
    print("=" * 70)
    print("FocusTrack - Desktop Core Test Mode")
    print("=" * 70)
    print(f"Platform: {platform.system()}")
    print(f"Input Monitoring: {'Enabled' if ENABLE_INPUT_MONITORING else 'Disabled (window-change detection only)'}")
    print(f"Idle Threshold: {IDLE_THRESHOLD_MINUTES} minutes")
    print("=" * 70)
    print("\nStarting tracking... Press Ctrl+C to stop.\n")
    
    try:
        start_monitoring()
        
        # Keep the main thread alive
        while tracking_active:
            time.sleep(1)
            
    except KeyboardInterrupt:
        print("\n\nStopping tracker...")
        stop_monitoring()
        print("Goodbye!")
