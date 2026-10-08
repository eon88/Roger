#!/bin/sh
set -eu

DATA_DIR="${DATA_DIR:-/data}"
mkdir -p "$DATA_DIR"

if [ ! -f "$DATA_DIR/stage.json" ]; then
  echo "Initialising Roger data store..."
  cp /app/stage.seed.json "$DATA_DIR/stage.json"
fi

if [ ! -f "$DATA_DIR/users.json" ]; then
  echo "Creating initial Roger portal accounts..."
  DATA_DIR="$DATA_DIR" python /app/make_users.py
  echo
  echo "IMPORTANT: save the generated passwords shown above."
  echo "They are generated only when users.json is first created."
fi

exec python /app/serve.py
