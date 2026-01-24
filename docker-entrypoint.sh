#!/bin/sh

# Exit immediately if a command exits with a non-zero status
set -e

# Function to wait for the database
wait_for_db() {
    echo "Waiting for PostgreSQL..."

    # Use python to check since it's guaranteed to be installed
    python << END
import sys
import time
import psycopg2
import os

db_name = os.environ.get("DB_NAME")
db_user = os.environ.get("DB_USER")
db_password = os.environ.get("DB_PASSWORD")
db_host = os.environ.get("DB_HOST")
db_port = os.environ.get("DB_PORT")

start_time = time.time()
while True:
    try:
        conn = psycopg2.connect(
            dbname=db_name,
            user=db_user,
            password=db_password,
            host=db_host,
            port=db_port
        )
        conn.close()
        print("PostgreSQL started")
        sys.exit(0)
    except psycopg2.OperationalError:
        if time.time() - start_time > 30:
            print("Timeout waiting for Database")
            sys.exit(1)
        time.sleep(1)
END
}

# Check if we are using SQLite or Postgres
if [ "$USE_SQLITE" != "True" ] && [ -n "$DB_HOST" ]; then
    wait_for_db
fi

# Execute the main command
exec "$@"
