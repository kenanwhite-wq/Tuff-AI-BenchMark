#!/bin/bash

cd /Users/kenan/Documents/Tuff-AI-BenchMark

# Create logs folder
mkdir -p logs

echo "🚀 Starting all services..."

# Start Flask API
echo "  📡 Starting Flask API on port 5001..."
nohup .venv-1/bin/python SimpleWeb > logs/flask.log 2>&1 &
FLASK_PID=$!

# Start React
echo "  🎨 Starting React on port 3000..."
cd frontend
nohup npm start > ../logs/react.log 2>&1 &
REACT_PID=$!
cd ..

# Start Scheduler (optional)
echo "  ⏰ Starting Scheduler..."
nohup .venv-1/bin/python Timer.py > logs/scheduler.log 2>&1 &
SCHEDULER_PID=$!

# Save PIDs to file
echo "FLASK_PID=$FLASK_PID" > .pids
echo "REACT_PID=$REACT_PID" >> .pids
echo "SCHEDULER_PID=$SCHEDULER_PID" >> .pids

echo ""
echo "✅ All services started!"
echo "   Flask API: http://localhost:5001"
echo "   React App: http://localhost:3000"
echo ""
echo "📝 Logs:"
echo "   Flask: tail -f logs/flask.log"
echo "   React: tail -f logs/react.log"
echo "   Scheduler: tail -f logs/scheduler.log"
echo ""
echo "🛑 To stop all: ./stop.sh"