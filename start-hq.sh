#!/bin/bash
# Start Hermes HQ and open in browser
python3 -m hermes_hq &
sleep 2
open http://127.0.0.1:8787
