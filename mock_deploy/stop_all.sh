#!/usr/bin/env bash
pkill -f "mock_deploy/server.py" && echo "stopped" || echo "nothing running"
