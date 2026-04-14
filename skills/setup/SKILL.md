---
name: setup
description: Configure always-on daemons via systemd, launchd, or Task Scheduler
---

# Daemon Manager Setup

Configure daemons to auto-start on boot using the OS service manager.

## Workflow

1. **Scan for daemons.** Call `daemon_list` to discover all known daemons, their running state, saved config (command/args/cwd), and whether they already have auto-start configured.

2. **Show status.** Present a table:

   | Daemon | Running | Auto-start | Service |
   |--------|---------|------------|---------|
   | (name) | yes/no  | yes/no     | systemd / launchd / none |

3. **Identify gaps.** Daemons that are known (have a PID file or config) but do NOT have auto-start configured need setup. If all daemons have auto-start, tell the user everything is configured and stop.

4. **If a specific daemon was requested** (user passed an argument or named one), set up just that one. Otherwise, offer to set up all daemons missing auto-start.

5. **Check for saved config.** Each daemon may have a saved config (command, args, cwd) from a prior `daemon_start` call. If config exists, use it — don't ask the user. If no config exists, ask the user for the command, args, and working directory.

6. **Generate and install the service.** Based on the detected OS:

### Linux (systemd)

Create `~/.config/systemd/user/{daemon_name}.service`:

```ini
[Unit]
Description={daemon_name} daemon
After=network.target

[Service]
Type=simple
ExecStart={command} {args}
WorkingDirectory={cwd}
Restart=on-failure
RestartSec=5
Environment=DAEMON_IPC_ADDRESS={ipc_address}

[Install]
WantedBy=default.target
```

Then enable and start:
```bash
systemctl --user daemon-reload
systemctl --user enable {daemon_name}
systemctl --user start {daemon_name}
loginctl enable-linger $USER
```

### macOS (launchd)

Create `~/Library/LaunchAgents/com.claude.daemon.{daemon_name}.plist`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.claude.daemon.{daemon_name}</string>
    <key>ProgramArguments</key>
    <array>
        <string>{command}</string>
        <!-- one <string> per arg -->
    </array>
    <key>WorkingDirectory</key>
    <string>{cwd}</string>
    <key>EnvironmentVariables</key>
    <dict>
        <key>DAEMON_IPC_ADDRESS</key>
        <string>{ipc_address}</string>
    </dict>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
</dict>
</plist>
```

Then load: `launchctl load ~/Library/LaunchAgents/com.claude.daemon.{daemon_name}.plist`

### Windows (Task Scheduler)

```powershell
$action = New-ScheduledTaskAction -Execute "{command}" -Argument "{args}" -WorkingDirectory "{cwd}"
$trigger = New-ScheduledTaskTrigger -AtLogOn
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -ExecutionTimeLimit 0
Register-ScheduledTask -TaskName "claude-daemon-{daemon_name}" -Action $action -Trigger $trigger -Settings $settings
```

7. **Verify.** Call `daemon_status` to confirm the daemon is running and IPC is reachable after the service starts.
