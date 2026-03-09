#!/bin/bash
# Start the IOEC application
set -e

# Load environment
if [ -f .env ]; then
    export $(cat .env | grep -v '^#' | xargs)
fi

# Initialize database
python -c "
import sys
sys.path.insert(0, '.')
from backend.db.session import init_db
init_db()
print('Database initialized.')
"

# Start Streamlit
streamlit run streamlit_app.py --server.port=${PORT:-8080} --server.address=0.0.0.0
