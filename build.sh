#!/bin/bash
set -e

python3 --version

echo "Building the project..."
python3 -m pip install -r requirements.txt --break-system-packages

echo "Collecting static files..."
python3 manage.py collectstatic --noinput --clear
