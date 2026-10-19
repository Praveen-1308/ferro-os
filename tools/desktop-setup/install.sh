#!/bin/bash
set -e

echo "--> Configuring FerroOS Desktop Environment..."

# Ensure ferro home directories
mkdir -p /home/ferro/Desktop
mkdir -p /home/ferro/Documents
mkdir -p /home/ferro/Projects
mkdir -p /home/ferro/.config/xfce4/xfconf/xfce-perchannel-xml

# Desktop shortcuts
cat << 'EOF' > /home/ferro/Desktop/thunar.desktop
[Desktop Entry]
Version=1.0
Type=Application
Name=File Manager
Comment=Browse files and folders
Exec=thunar /home/ferro
Icon=system-file-manager
Terminal=false
Categories=System;FileManager;
EOF

cat << 'EOF' > /home/ferro/Desktop/galculator.desktop
[Desktop Entry]
Version=1.0
Type=Application
Name=Calculator
Comment=Perform calculations
Exec=galculator
Icon=accessories-calculator
Terminal=false
Categories=Utility;Calculator;
EOF

cat << 'EOF' > /home/ferro/Desktop/mousepad.desktop
[Desktop Entry]
Version=1.0
Type=Application
Name=Text Editor
Comment=Edit text files and code
Exec=mousepad /home/ferro/Documents/Welcome_to_FerroOS.txt
Icon=accessories-text-editor
Terminal=false
Categories=Utility;TextEditor;
EOF

cat << 'EOF' > /home/ferro/Desktop/xfce4-taskmanager.desktop
[Desktop Entry]
Version=1.0
Type=Application
Name=Task Manager
Comment=Monitor CPU, Memory and Running Tasks
Exec=xfce4-taskmanager
Icon=utilities-system-monitor
Terminal=false
Categories=System;Monitor;
EOF

cat << 'EOF' > /home/ferro/Desktop/xfce4-terminal.desktop
[Desktop Entry]
Version=1.0
Type=Application
Name=FerroOS Terminal
Comment=Command line terminal
Exec=xfce4-terminal
Icon=utilities-terminal
Terminal=false
Categories=System;TerminalEmulator;
EOF

cat << 'EOF' > /home/ferro/Desktop/python-gui.desktop
[Desktop Entry]
Version=1.0
Type=Application
Name=Python GUI App
Comment=Interactive Python Tkinter Demo
Exec=python3 /home/ferro/Projects/gui_demo.py
Icon=python3
Terminal=false
Categories=Development;
EOF

# Make desktop files executable
chmod +x /home/ferro/Desktop/*.desktop

# Welcome text file
cat << 'EOF' > /home/ferro/Documents/Welcome_to_FerroOS.txt
===================================================================
                  Welcome to FerroOS Desktop!
===================================================================

FerroOS provides a full-featured, modern graphical operating
system environment running natively in your browser:

  * Window Management: Drag, snap, resize, minimize, maximize.
  * Start Menu: Click the Application menu in the top/bottom panel.
  * File Manager: Full Thunar file explorer with drag & drop.
  * System Tools: Task manager with live CPU and memory graphs.
  * Productivity: Calculator, text editor with syntax highlighting.
  * Development: Python 3 with Tkinter GUI toolkit, Shell, Rust.

Enjoy your FerroOS live desktop session!
EOF

# Python Tkinter GUI Demo
cat << 'EOF' > /home/ferro/Projects/gui_demo.py
import tkinter as tk
from tkinter import ttk, messagebox
import time

def calculate():
    try:
        val = eval(entry.get())
        result_label.config(text=f"Result: {val}", foreground="green")
    except Exception as e:
        result_label.config(text=f"Error: {e}", foreground="red")

root = tk.Tk()
root.title("FerroOS Interactive Python App")
root.geometry("450x300")
root.configure(bg="#1e1e2e")

style = ttk.Style()
style.theme_use('clam')

title_lbl = tk.Label(root, text="FerroOS GUI Demo", font=("Helvetica", 16, "bold"), fg="#cdd6f4", bg="#1e1e2e")
title_lbl.pack(pady=15)

info_lbl = tk.Label(root, text="Enter any Python math expression:", font=("Helvetica", 11), fg="#bac2de", bg="#1e1e2e")
info_lbl.pack(pady=5)

entry = tk.Entry(root, font=("Helvetica", 12), width=28, justify="center")
entry.insert(0, "42 * 1337 + 7")
entry.pack(pady=8)

btn = tk.Button(root, text="Evaluate Expression", command=calculate, bg="#89b4fa", fg="#11111b", font=("Helvetica", 11, "bold"), padx=10, pady=5)
btn.pack(pady=10)

result_label = tk.Label(root, text="Result: Click Evaluate", font=("Helvetica", 12, "bold"), fg="#f9e2af", bg="#1e1e2e")
result_label.pack(pady=10)

root.mainloop()
EOF

# Set ownership
chown -R ferro:ferro /home/ferro

echo "--> FerroOS Desktop environment successfully prepared."
