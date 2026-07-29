#!/usr/bin/env bash
# Render build script

set -o errexit

pip install -r requirements.txt

# Create data directory if it doesn't exist
mkdir -p /data
