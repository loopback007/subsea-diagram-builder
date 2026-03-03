#!/bin/bash

for i in {1..5}; do
  curl -X POST http://192.168.1.55:8080/api/generate \
    -H "Content-Type: application/json" \
    -d @topology_payload.json \
    -o /dev/null \
    -w "Request $i HTTP Code: %{http_code}\n" &
done

# Wait for all background curl processes to finish before exiting
wait
echo "Stress test complete."