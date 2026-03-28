#!/bin/bash

# Configuration
PROJECT_ID="billing_v2"
# This finds ALL python files, excluding hidden folders or venvs to keep it clean
FILES_TO_INDEX=$(find /opt/billing_v2/ -name "*.py" -not -path "*/.*" -not -path "*venv*")

echo "📂 Scanning /opt/billing_v2/ for Python files..."

for file in $FILES_TO_INDEX; do
    # Get a clean name for the Archon document title
    RELATIVE_PATH=${file#/opt/billing_v2/}
    
    echo "Indexing: $RELATIVE_PATH"
    
    # Read content and escape single quotes for the CLI command
    CONTENT=$(cat "$file" | sed "s/'/\\\\'/g")
    
    # Send to Archon
    gemini "Archon, use manage_document to 'create' a document in project '$PROJECT_ID'. 
    Title: '$RELATIVE_PATH', 
    document_type: 'source_code', 
    content: '$CONTENT'"
done

echo "✅ Indexing complete. Archon is now up to speed!"