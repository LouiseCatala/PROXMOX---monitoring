# The SIS 3.6 — live monitoring and alarm settings
Stop logger/viewer with Ctrl+C. Extract this ZIP outside the installed project; run install_upgrade.cmd. Restart logger.py and viewer.py. Press Ctrl+F5; footer must show Build SIS 3.6.

Demo mode, synthetic input controls and demo endpoints have been removed. Only live VM measurements are collected and displayed. Existing historical data is preserved, including old simulation records, but live dashboard/exports exclude those old simulation records.

Settings applies globally to all three VMs. Enter Low, Warning and Critical start percentages for CPU, RAM, disk. Require 0 < Low < Warning < Critical <= 100. Save thresholds permanently writes threshold_settings.json; logger reads it each monitoring cycle. Restart retains custom settings. Source files do not need manual editing. Historical records retain their original severity.

Official defaults: CPU 60/70/85; RAM 60/70/85; disk 60/75/90. Normal is below Low. Low is below Warning. Warning is below Critical. Critical includes its boundary and above. Load official defaults fills inputs; Save applies. Upgrades preserve existing saved custom thresholds.

For an alarm presentation with measured RAM near 33%, use RAM Low=10, Warning=20, Critical=40 and Save for a warning. Change Critical=30 and Save for critical. Enable alarm sound. Allow a new logger check and dashboard poll (usually 5–10 seconds, more with slow endpoints). Offline/stale nodes stay silent. Return to official defaults and Save after presentation.

Mobile hotspot: Windows dashboard and PostgreSQL use localhost. VMs and Windows communicate over VirtualBox Host-Only 192.168.56.0/24, independent of Wi-Fi. Keep the Host-Only adapter enabled and VM addresses unchanged. The NAT adapter uses the current internet connection. No internet is needed for installed local code and bundled audio. Do not expose services or switch adapters to Bridged for the presentation. If the hotspot uses the same 192.168.56.0/24 subnet, resolve the route overlap before presenting.
