#!/bin/bash

echo "🛑 Stopping all services..."

# Kill by port
echo "  Clearing ports..."
lsof -ti:5001 | xargs kill -9 2>/dev/null
lsof -ti:3000 | xargs kill -9 2>/dev/null

# Kill by process name as backup
pkill -9 -f SimpleWeb 2>/dev/null
pkill -9 -f "react-scripts" 2>/dev/null
pkill -9 -f "Timer.py" 2>/dev/null
pkill -9 -f "hourlyfetcher.py" 2>/dev/null

# Clean up PID file
rm -f .pids

# Wait to confirm ports are free
sleep 2

# Verify
PORT_3000=$(lsof -ti:3000)
PORT_5001=$(lsof -ti:5001)

if [ -z "$PORT_3000" ] && [ -z "$PORT_5001" ]; then
    echo "✅ All services stopped, ports are clear"
else
    echo "⚠️ Some processes may still be running"
    echo "   Port 3000: ${PORT_3000:-clear}"
    echo "   Port 5001: ${PORT_5001:-clear}"
fi