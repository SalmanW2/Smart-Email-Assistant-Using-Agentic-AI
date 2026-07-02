#!/bin/bash
apt-get update && apt-get install -y ffmpeg
pip install -r backend/requirements.txt
