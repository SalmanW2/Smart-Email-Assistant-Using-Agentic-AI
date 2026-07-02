import re

try:
    with open('database/schema.sql', 'r', encoding='utf-8') as f:
        content = f.read()

    # Remove saved_attachments table
    content = re.sub(r'CREATE TABLE IF NOT EXISTS saved_attachments.*?\);', '', content, flags=re.DOTALL)

    # Remove saved_attachments indexes and RLS
    content = re.sub(r'CREATE INDEX idx_saved_attachments.*?;', '', content)
    content = re.sub(r'ALTER TABLE saved_attachments ENABLE ROW LEVEL SECURITY;', '', content)
    content = re.sub(r'CREATE POLICY "Tenant-Isolation-Policy-SavedAttachments".*?;', '', content)

    # Make sure pgvector extension exists
    if 'CREATE EXTENSION IF NOT EXISTS vector;' not in content:
        content = content.replace('CREATE EXTENSION IF NOT EXISTS pg_trgm;', 
                                'CREATE EXTENSION IF NOT EXISTS pg_trgm;\nCREATE EXTENSION IF NOT EXISTS vector;')

    with open('database/schema.sql', 'w', encoding='utf-8') as f:
        f.write(content)
        
    print('Cleaned up schema.sql')
except Exception as e:
    print(f"Error: {e}")
