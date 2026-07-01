#!/bin/bash
set -e

echo "==================================="
echo "🚀 Pre-start Build Script"
echo "==================================="

# 1. Build the Frontend
echo "[1/2] Building Node.js Frontend (Vite)..."
cd frontend
npm install
npm run build
cd ..

# 2. Install Backend Dependencies
echo "[2/2] Installing Python Backend Dependencies..."
pip install -r backend/requirements.txt

echo "==================================="
echo "✅ Build Complete. Ready for Uvicorn."
echo "==================================="
