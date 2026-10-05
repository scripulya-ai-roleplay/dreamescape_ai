CREATE TABLE IF NOT EXISTS chat_summaries (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    chat_id UUID NOT NULL REFERENCES chats(id) ON DELETE CASCADE,
    content TEXT,
    status VARCHAR(20) NOT NULL DEFAULT 'queued' CHECK (status IN ('queued', 'pending', 'completed', 'failed')),
    llm_model VARCHAR(100) NOT NULL,
    from_message_id UUID REFERENCES messages(id) ON DELETE SET NULL,
    until_message_id UUID REFERENCES messages(id) ON DELETE SET NULL,
    covered_from_at TIMESTAMP WITH TIME ZONE NOT NULL,
    covered_until_at TIMESTAMP WITH TIME ZONE NOT NULL,
    messages_count INTEGER NOT NULL,
    source_tokens INTEGER NOT NULL,
    summary_tokens INTEGER,
    error TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_chat_summaries_chat_id ON chat_summaries(chat_id, covered_from_at);

ALTER TABLE messages ADD COLUMN IF NOT EXISTS is_archived BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE messages ADD COLUMN IF NOT EXISTS summary_id UUID REFERENCES chat_summaries(id) ON DELETE SET NULL;

CREATE INDEX IF NOT EXISTS idx_messages_summary_id ON messages(summary_id);
