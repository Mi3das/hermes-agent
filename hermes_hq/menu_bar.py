#!/usr/bin/env python3
"""
Hermes HQ Menu Bar Integration for macOS
Shows HQ status in the menu bar and provides quick access to dashboard
"""

import subprocess
import json
import sys
from pathlib import Path

def get_hq_status():
    """Get current HQ status from API"""
    try:
        result = subprocess.run(
            ['curl', '-s', 'http://localhost:8787/api/info'],
            capture_output=True,
            timeout=2,
            text=True
        )
        if result.returncode == 0:
            data = json.loads(result.stdout)
            return {
                'online': data.get('online', False),
                'ready': data.get('ready', False),
                'provider': data.get('provider', 'unknown'),
                'model': data.get('model', 'unknown').split('/')[-1],
            }
    except Exception:
        pass
    return None

def get_ecosystem_health():
    """Get ecosystem health from API"""
    try:
        result = subprocess.run(
            ['curl', '-s', 'http://localhost:8787/api/ecosystem/health'],
            capture_output=True,
            timeout=2,
            text=True
        )
        if result.returncode == 0:
            return json.loads(result.stdout)
    except Exception:
        pass
    return None

def format_status_line():
    """Format status for menu bar display"""
    status = get_hq_status()
    if not status:
        return "🔴 HQ Offline | Open Dashboard"
    
    if status['ready']:
        health = get_ecosystem_health()
        if health:
            agents = health.get('total_agents', 0)
            success_rate = health.get('avg_success_rate', 0)
            return f"🟢 HQ Ready • {agents} agents • {success_rate:.0%} success | Dashboard"
        return f"🟢 HQ Ready • {status['model']} | Dashboard"
    
    return "🟡 HQ Starting | Dashboard"

def open_dashboard():
    """Open HQ dashboard in default browser"""
    subprocess.run(['open', 'http://localhost:8787'])

def start_hq():
    """Start HQ if not running"""
    status = get_hq_status()
    if not status:
        subprocess.Popen([
            'bash', '-c',
            'source ~/.hermes-agent/.venv/bin/activate && python -m hermes_hq'
        ])

if __name__ == '__main__':
    if len(sys.argv) > 1:
        if sys.argv[1] == 'status':
            print(format_status_line())
        elif sys.argv[1] == 'dashboard':
            open_dashboard()
        elif sys.argv[1] == 'start':
            start_hq()
    else:
        # Default: show status
        print(format_status_line())
