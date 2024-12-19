#!/bin/bash -ev

PORT=${PORT:-8080}

exec streamlit run map.py --server.address=0.0.0.0 --server.port=${PORT}
