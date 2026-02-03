"""
FocusTrack - Desktop GUI Application
Modern CustomTkinter-based GUI for professional look and feel.
"""

import customtkinter as ctk
import tkinter as tk
from tkinter import messagebox
import threading
import time
from datetime import datetime, timedelta
import uuid
import sys
import os

# Import our modules
import tracker_core
from local_db import LocalDB
from sync import SyncManager, SyncConfig

# Set theme
ctk.set_appearance_mode("System")  # Modes: "System" (standard), "Dark", "Light"
ctk.set_default_color_theme("blue")  # Themes: "blue" (standard), "green", "dark-blue"


class FocusTrackApp(ctk.CTk):
    """Main application window for Workwise with Modern UI."""
    
    def __init__(self):
        super().__init__()
        
        # Initialize Core Logic
        self.db = LocalDB()
        self.config = SyncConfig()
        self.sync_manager = SyncManager(
            db=self.db,
            api_base_url=self.config.api_url,
            sync_interval=60
        )
        
        if self.config.token:
            self.sync_manager.set_token(self.config.token)
        
        self.session_id = None
        self.start_time = None
        self.is_tracking = False
        
        # Window Setup
        self.title("Workwise Agent")
        self.geometry("600x400") # Smaller default size since we removed content
        self.minsize(500, 350)
        
        # Configure Grid Layout (2 columns: Sidebar, Main Content)
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)
        
        # Setup UI Components
        self._setup_sidebar()
        self._setup_main_area()
        
        # Connect Core Callbacks
        tracker_core.on_data_collected = self._on_data_collected
        
        # Start Background Sync
        if self.config.token:
            self.sync_manager.start_background_sync()
        
        # Start UI Update Loops
        self._update_stats_loop()
        
        # Protocol Handlers
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        
        # macOS: Force window to appear and get focus
        self.after(100, self._force_window_focus)

    def _setup_sidebar(self):
        """Create the left sidebar for navigation and info."""
        self.sidebar_frame = ctk.CTkFrame(self, width=180, corner_radius=0)
        self.sidebar_frame.grid(row=0, column=0, sticky="nsew")
        self.sidebar_frame.grid_rowconfigure(4, weight=1)
        
        # Logo Label (Rebranded)
        self.logo_label = ctk.CTkLabel(
            self.sidebar_frame, 
            text="Workwise", 
            font=ctk.CTkFont(size=24, weight="bold")
        )
        self.logo_label.grid(row=0, column=0, padx=20, pady=(20, 10))
        
        # Sidebar Buttons
        self.sidebar_home_btn = ctk.CTkButton(
            self.sidebar_frame, 
            text="Home", 
            command=self._show_home,
            fg_color="transparent", 
            border_width=2, 
            text_color=("gray10", "#DCE4EE")
        )
        self.sidebar_home_btn.grid(row=1, column=0, padx=20, pady=10)
        
        self.sidebar_settings_btn = ctk.CTkButton(
            self.sidebar_frame, 
            text="Settings", 
            command=self._show_settings,
            fg_color="transparent", 
            border_width=2, 
            text_color=("gray10", "#DCE4EE")
        )
        self.sidebar_settings_btn.grid(row=2, column=0, padx=20, pady=10)
        
        # Status Section (Bottom of Sidebar)
        self.user_label = ctk.CTkLabel(
            self.sidebar_frame, 
            text="Not Logged In",
            font=ctk.CTkFont(size=12)
        )
        self.user_label.grid(row=5, column=0, padx=20, pady=(10, 20))
        
        # Removed prominent sync status from sidebar to simplify

    def _setup_main_area(self):
        """Create the main content area."""
        
        # HOME FRAME
        self.home_frame = ctk.CTkFrame(self, corner_radius=0, fg_color="transparent")
        self.home_frame.grid(row=0, column=1, sticky="nsew")
        self.home_frame.grid_columnconfigure(0, weight=1)
        self.home_frame.grid_rowconfigure(0, weight=1) # Center vertically
        
        # Center Container
        self.center_container = ctk.CTkFrame(self.home_frame, fg_color="transparent")
        self.center_container.grid(row=0, column=0)
        
        # -- Timer / Status Section --
        self.status_label = ctk.CTkLabel(
            self.center_container,
            text="Ready to Start?",
            font=ctk.CTkFont(size=20)
        )
        self.status_label.pack(pady=(0, 20))
        
        self.timer_label = ctk.CTkLabel(
            self.center_container,
            text="00:00:00",
            font=ctk.CTkFont(size=72, weight="bold")
        )
        self.timer_label.pack(pady=(0, 30))
        
        # -- Controls --
        self.start_button = ctk.CTkButton(
            self.center_container,
            text="START WORK",
            font=ctk.CTkFont(size=18, weight="bold"),
            width=220,
            height=60,
            corner_radius=30,
            fg_color="#10B981",  # Green
            hover_color="#059669",
            command=self._start_tracking
        )
        self.start_button.pack(padx=20, pady=10)
        
        self.stop_button = ctk.CTkButton(
            self.center_container,
            text="STOP WORK",
            font=ctk.CTkFont(size=18, weight="bold"),
            width=220,
            height=60,
            corner_radius=30,
            fg_color="#EF4444",  # Red
            hover_color="#DC2626",
            command=self._stop_tracking
        )
        # Initially hidden/packed in toggle logic
        
        # Removed Recent Activity / Stats frame entirely as requested
        
        # SETTINGS FRAME (Hidden initially)
        self.settings_frame = ctk.CTkFrame(self, corner_radius=0, fg_color="transparent")
        
        self._setup_settings_ui()
        
    def _setup_settings_ui(self):
        """Build the settings interface."""
        self.settings_frame.grid_columnconfigure(0, weight=1)
        
        title = ctk.CTkLabel(
            self.settings_frame,
            text="Settings & Account",
            font=ctk.CTkFont(size=20, weight="bold")
        )
        title.grid(row=0, column=0, padx=20, pady=20, sticky="w")
        
        # Form Container
        form_frame = ctk.CTkFrame(self.settings_frame)
        form_frame.grid(row=1, column=0, padx=20, pady=10, sticky="ew")
        
        # Email
        ctk.CTkLabel(form_frame, text="Email:").pack(anchor="w", padx=20, pady=5)
        self.email_entry = ctk.CTkEntry(form_frame, width=400)
        if self.config.email:
            self.email_entry.insert(0, self.config.email)
        self.email_entry.pack(anchor="w", padx=20, pady=(0, 15))
        
        # Password
        ctk.CTkLabel(form_frame, text="Password:").pack(anchor="w", padx=20, pady=5)
        self.pass_entry = ctk.CTkEntry(form_frame, width=400, show="*")
        self.pass_entry.pack(anchor="w", padx=20, pady=(0, 20))
        
        # Login Button
        self.settings_login_btn = ctk.CTkButton(
            form_frame,
            text="Login & Save",
            command=self._perform_login
        )
        self.settings_login_btn.pack(anchor="w", padx=20, pady=(0, 20))
        
        # Login Status Message
        self.login_message = ctk.CTkLabel(form_frame, text="", text_color="red")
        self.login_message.pack(anchor="w", padx=20, pady=(0, 20))

    def _setup_login_window(self):
        """Deprecated."""
        pass

    def _force_window_focus(self):
        """Force window to appear on macOS when launched from Finder/Dock."""
        try:
            # Bring window to front
            self.lift()
            self.attributes('-topmost', True)
            self.after(200, lambda: self.attributes('-topmost', False))
            
            # Ensure window is visible
            self.deiconify()
            self.focus_force()
            
            # macOS-specific: Use AppleScript to activate the app
            import subprocess
            subprocess.run([
                'osascript', '-e',
                'tell application "System Events" to set frontmost of process "WorkwiseAgent" to true'
            ], capture_output=True)
        except Exception as e:
            print(f"[Window] Focus error: {e}")

    # -- Navigation --
    def _show_home(self):
        self.settings_frame.grid_forget()
        self.home_frame.grid(row=0, column=1, sticky="nsew")
        self.sidebar_home_btn.configure(fg_color=("gray75", "gray25"))
        self.sidebar_settings_btn.configure(fg_color="transparent")

    def _show_settings(self):
        self.home_frame.grid_forget()
        self.settings_frame.grid(row=0, column=1, sticky="nsew")
        self.sidebar_settings_btn.configure(fg_color=("gray75", "gray25"))
        self.sidebar_home_btn.configure(fg_color="transparent")

    # -- Logic --
    def _perform_login(self):
        # URL is loaded from sync_config.json (Hidden from UI)
        url = self.config.api_url
        email = self.email_entry.get().strip()
        password = self.pass_entry.get()
        
        if not all([url, email, password]):
            self.login_message.configure(text="Email and Password required", text_color="red")
            return
            
        self.login_message.configure(text="Logging in...", text_color="blue")
        self.update()
        
        # Update config
        self.config.api_url = url
        self.config.email = email
        self.sync_manager.api_base_url = url
        
        if self.sync_manager.login(email, password):
            self.config.token = self.sync_manager.auth_token
            self.config.save_config()
            self.sync_manager.start_background_sync()
            
            self.login_message.configure(text="Success! Logged in.", text_color="green")
            self.user_label.configure(text=f"User: {email}")
            self._show_home()
        else:
            self.login_message.configure(text="Login Failed. Check credentials.", text_color="red")

    def _start_tracking(self):
        if self.is_tracking: return
        
        self.is_tracking = True
        self.session_id = str(uuid.uuid4())
        self.start_time = datetime.now()
        
        # UI Updates: Hide Start, Show Stop
        self.status_label.configure(text="Work in Progress...")
        self.status_label.configure(text_color="#10B981") # Green
        
        self.start_button.pack_forget()
        self.stop_button.configure(state="normal", fg_color="#EF4444")
        self.stop_button.pack(padx=20, pady=10)
        
        tracker_core.start_monitoring()
        print(f"[Session] Started: {self.session_id}")

    def _stop_tracking(self):
        if not self.is_tracking: return
        
        self.is_tracking = False
        tracker_core.stop_monitoring()
        
        # UI Updates: Hide Stop, Show Start
        self.status_label.configure(text="Session Paused")
        self.status_label.configure(text_color="gray")
        
        self.stop_button.pack_forget()
        self.start_button.configure(state="normal", fg_color="#10B981")
        self.start_button.pack(padx=20, pady=10)
        
        self.session_id = None
        self.start_time = None

    def _on_data_collected(self, data: dict):
        try:
            data["session_id"] = self.session_id
            self.db.save_log(data)
        except Exception as e:
            print(f"[DB] Error saving log: {e}")

    def _update_stats_loop(self):
        try:
            # 1. Update Timer
            if self.is_tracking and self.start_time:
                elapsed = datetime.now() - self.start_time
                total_seconds = int(elapsed.total_seconds())
                formatted_time = str(timedelta(seconds=total_seconds))
                self.timer_label.configure(text=formatted_time)
            
            # 2. Sync Status - Only show if user is logged in (Top left)
            # We removed the visual label, so we just update the user label if needed
            if self.config.email:
                 self.user_label.configure(text=f"User: {self.config.email}")
            else:
                self.user_label.configure(text="Not Logged In")

        except Exception as e:
            print(f"Error in stats loop: {e}")
            
        self.after(1000, self._update_stats_loop)

    def _on_close(self):
        if self.is_tracking:
            if not messagebox.askyesno("Exit?", "Tracking is active. Stop and exit?"):
                return
            self._stop_tracking()
        
        self.sync_manager.stop_background_sync()
        self.destroy()

    def run(self):
        self.mainloop()


if __name__ == "__main__":
    print("Starting FocusTrack (Modern UI)...")
    app = FocusTrackApp()
    app.run()
