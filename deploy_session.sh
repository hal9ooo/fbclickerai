#!/bin/bash
# Deploy session file to remote server and restart container
# Usage: ./deploy_session.sh [remote_user@host]

REMOTE="${1:-root@192.168.1.203}"
SESSION_FILE="data/sessions/facebook_session.json"
REMOTE_PATH="/root/progetti/dev/fbclicker/data/sessions"
REMOTE_CONTAINER_PATH="/app/data/sessions"

echo "🚀 Deploying session to $REMOTE"
echo ""

# Check if session file exists
if [ ! -f "$SESSION_FILE" ]; then
    echo "❌ Session file not found: $SESSION_FILE"
    echo "   Run ./manual_login_mac.sh first to create it."
    exit 1
fi

echo "📁 Session file: $SESSION_FILE"
echo "📡 Remote: $REMOTE"
echo ""

# Create remote directory if it doesn't exist
echo "📂 Creating remote directory..."
ssh "$REMOTE" "mkdir -p $REMOTE_PATH"

# Copy session file
echo "📤 Copying session file..."
scp "$SESSION_FILE" "$REMOTE:$REMOTE_PATH/"

if [ $? -eq 0 ]; then
    echo "✅ Session file copied successfully"
    echo ""
    
    # Verify file in container
    echo "🔍 Verifying file in container..."
    ssh "$REMOTE" "docker exec fbclicker ls -la $REMOTE_CONTAINER_PATH/facebook_session.json"
    
    # Restart container
    echo "🔄 Restarting fbclicker container..."
    ssh "$REMOTE" "docker restart fbclicker"
    
    if [ $? -eq 0 ]; then
        echo "✅ Container restarted"
        echo ""
        echo "🎉 Done! Session deployed and container restarted."
    else
        echo "⚠️  Container restart failed. Please check manually."
        exit 1
    fi
else
    echo "❌ Failed to copy session file"
    exit 1
fi
