---
name: setup
description: Configure always-on daemons via systemd, launchd, or Task Scheduler
---

# Daemon Manager Setup

Guide the user through configuring a daemon to run permanently (always-on) using their OS service manager.

## Steps

1. Ask which daemon to configure (daemon_name, command, args, cwd)
2. Detect the OS using `daemon_status` or check `platform`
3. Generate the appropriate service configuration:

### Linux (systemd)

Create a unit file at `~/.config/systemd/user/{daemon_name}.service`:

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
# Enable lingering so it runs without an active login session:
loginctl enable-linger $USER
```

### macOS (launchd)

Create a plist at `~/Library/LaunchAgents/com.claude.daemon.{daemon_name}.plist`:

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

Guide the user to create a scheduled task:
```powershell
$action = New-ScheduledTaskAction -Execute "{command}" -Argument "{args}" -WorkingDirectory "{cwd}"
$trigger = New-ScheduledTaskTrigger -AtLogOn
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -ExecutionTimeLimit 0
Register-ScheduledTask -TaskName "claude-daemon-{daemon_name}" -Action $action -Trigger $trigger -Settings $settings
```

4. After generating the config, verify the daemon is running with `daemon_status`
5. Confirm the setup is working by checking IPC reachability
