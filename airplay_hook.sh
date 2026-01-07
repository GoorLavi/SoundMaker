#!/bin/bash
# AirPlay Hook Script for SoundMaker
# Called by shairport-sync when AirPlay devices connect/disconnect
# Writes events to named pipe for audio_controller to read

PIPE="/tmp/soundmaker_airplay_events"
EVENT="$1"

# Validate event type
if [ "$EVENT" != "connect" ] && [ "$EVENT" != "disconnect" ]; then
    logger -t soundmaker "AirPlay hook: Invalid event '$EVENT'"
    exit 1
fi

# Write event to pipe if it exists
if [ -p "$PIPE" ]; then
    # Write in background to avoid blocking, with timeout
    (
        echo "$EVENT" > "$PIPE" 2>/dev/null
    ) &
    WRITE_PID=$!
    
    # Wait up to 0.5 seconds for write to complete
    sleep 0.5
    
    # Kill if still running (means it blocked or failed)
    if kill -0 $WRITE_PID 2>/dev/null; then
        kill $WRITE_PID 2>/dev/null
        wait $WRITE_PID 2>/dev/null
        logger -t soundmaker "AirPlay hook: Write to pipe timed out for '$EVENT'"
    else
        # Write completed successfully
        wait $WRITE_PID 2>/dev/null
        logger -t soundmaker "AirPlay hook: Sent '$EVENT' event to pipe"
    fi
else
    # Pipe doesn't exist yet (SoundMaker may not be running)
    logger -t soundmaker "AirPlay hook: $EVENT (pipe not found: $PIPE)"
fi

exit 0

