# Hermes HQ - macOS Desktop Setup Guide

## 🚀 Quick Launch Options

### Option 1: Desktop Launcher (Easiest)

1. Double-click: **Launch_HQ_Dashboard.command** on your Desktop
2. This opens a terminal window that starts Hermes HQ with all upgraded systems
3. Click the URL in the terminal or open http://localhost:8787 in your browser

### Option 2: Terminal Command

```bash
cd ~/.hermes-agent
source .venv/bin/activate
python -m hermes_hq
```

### Option 3: Alias (Fastest)

Add to `~/.zshrc` or `~/.bash_profile`:

```bash
alias hermes-hq="cd ~/.hermes-agent && source .venv/bin/activate && python -m hermes_hq"
```

Then just type: `hermes-hq`

---

## 📱 Menu Bar Integration

### Check HQ Status in Menu Bar

```bash
python ~/.hermes-agent/hermes_hq/menu_bar.py status
```

Output examples:
- 🟢 HQ Ready • 5 agents • 83% success
- 🟡 HQ Starting
- 🔴 HQ Offline

### Open Dashboard from Menu

```bash
python ~/.hermes-agent/hermes_hq/menu_bar.py dashboard
```

---

## 🎯 Using the Upgraded App

### 1. Load Demo Data (First Time)

```bash
python -m hermes_hq.seed_demo
```

This creates 5 agents with 20 missions each for testing.

### 2. Start Dashboard

```bash
python -m hermes_hq
# Opens at http://localhost:8787
```

### 3. Query the APIs

```bash
# Ecosystem health
curl http://localhost:8787/api/ecosystem/health | jq

# Top agent profile
curl http://localhost:8787/api/agents/agent-005/profile | jq

# Optimization priorities
curl http://localhost:8787/api/ecosystem/optimization-priorities | jq
```

---

## 📊 Dashboard Features

### Main Views

**Agent Profiles**
- Mission history and success rates
- Skill proficiency scores
- Specialization analysis
- Optimization recommendations

**Ecosystem Health**
- Overall success rate across all agents
- Health score per agent
- Specialization distribution
- Optimization priorities

**Adaptive Systems**
- Capability progression
- Runtime adaptations
- Communication personas
- Experience patterns

---

## 🔧 Keyboard Shortcuts

| Shortcut | Action |
|----------|--------|
| Cmd+R | Refresh dashboard |
| Cmd+K | Search agents |
| Cmd+, | Settings |
| Cmd+Q | Quit HQ |

---

## 📍 File Locations

**Application Code**
```
~/.hermes-agent/hermes_hq/
  ├── self_improvement.py       (Agent learning)
  ├── performance.py            (Analytics)
  ├── adaptive.py               (Adaptation)
  ├── server.py                 (API server)
  └── menu_bar.py               (Menu integration)
```

**Data Storage**
```
~/.hermes/hermes_hq/
  ├── self_improvement/
  │   └── learning_state.json   (Agent profiles)
  ├── missions.json             (Mission history)
  └── schedules.json            (Recurring tasks)
```

**Desktop Shortcuts**
```
~/Desktop/
  ├── Launch_HQ_Dashboard.command
  └── HERMES HQ.app
```

---

## 🆘 Troubleshooting

### Dashboard Won't Load

```bash
# Check if app is running
ps aux | grep "hermes_hq" | grep -v grep

# Manual start
cd ~/.hermes-agent
source .venv/bin/activate
python -m hermes_hq
```

### API Returns 404

```bash
# Wait for startup (takes 2-3 seconds)
sleep 3
curl http://localhost:8787/api/info
```

### Port Already in Use

```bash
# Find what's using port 8787
lsof -i :8787

# Kill previous process
pkill -f "python -m hermes_hq"
```

### Clear Old Data

```bash
rm ~/.hermes/hermes_hq/self_improvement/learning_state.json
# Then restart and seed demo data again
```

---

## 🎓 Documentation

- **API Reference**: `~/.hermes-agent/hermes_hq/SELF_IMPROVEMENT.md`
- **Architecture**: `~/.hermes-agent/TECHNICAL_ARCHITECTURE.md`
- **Deployment**: `~/.hermes-agent/DEPLOYMENT_GUIDE.md`

---

## 🌟 Advanced: Autostart on Login

### Method 1: LaunchAgent (Recommended)

```bash
# Create launch configuration
mkdir -p ~/Library/LaunchAgents

cat > ~/Library/LaunchAgents/com.hermes.hq.plist << 'EOF'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.hermes.hq</string>
    <key>ProgramArguments</key>
    <array>
        <string>/bin/bash</string>
        <string>-c</string>
        <string>cd ~/.hermes-agent && source .venv/bin/activate && python -m hermes_hq</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>StandardOutPath</key>
    <string>/tmp/hermes-hq.log</string>
    <key>StandardErrorPath</key>
    <string>/tmp/hermes-hq-error.log</string>
</dict>
</plist>
EOF

# Load it
launchctl load ~/Library/LaunchAgents/com.hermes.hq.plist
```

### Method 2: Add to Login Items

1. System Preferences → General → Login Items
2. Click "+" and select `/Users/ma-chete/Desktop/Launch_HQ_Dashboard.command`

---

## 📞 Support

For issues or questions:
- Check `/tmp/hermes-hq.log` for logs
- Review `DEPLOYMENT_GUIDE.md` for detailed help
- Email logs to support if needed

---

**Status**: ✅ Ready to use  
**Last Updated**: June 13, 2026  
**Version**: 1.0
