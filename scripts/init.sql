-- Database initialization script for scripulya_ai
-- Creates tables and inserts test data

-- Enable UUID generation extension
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- Drop tables if they exist (for clean initialization)
DROP TABLE IF EXISTS media_assets CASCADE;
DROP TABLE IF EXISTS messages CASCADE;
DROP TABLE IF EXISTS chats CASCADE;
DROP TABLE IF EXISTS scenes CASCADE;
DROP TABLE IF EXISTS characters CASCADE;
DROP TABLE IF EXISTS users CASCADE;

-- Create users table
CREATE TABLE users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    test_username VARCHAR(255),
    google_id VARCHAR(255) UNIQUE,
    crystal_balance INTEGER DEFAULT 1000
);

-- Create characters table
CREATE TABLE characters (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    owner_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name VARCHAR(255) NOT NULL,
    system_prompt TEXT NOT NULL,
    is_public BOOLEAN DEFAULT false
);

-- Create scenes table
CREATE TABLE scenes (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    owner_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    title VARCHAR(255) NOT NULL,
    background_prompt TEXT NOT NULL
);

-- Create chats table
CREATE TABLE chats (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    character_id UUID NOT NULL REFERENCES characters(id) ON DELETE CASCADE,
    scene_id UUID REFERENCES scenes(id) ON DELETE SET NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Create index on user_id for chats
CREATE INDEX idx_chats_user_id ON chats(user_id);

-- Create messages table
CREATE TABLE messages (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    chat_id UUID NOT NULL REFERENCES chats(id) ON DELETE CASCADE,
    role VARCHAR(50) NOT NULL CHECK (role IN ('user', 'model', 'system')),
    content TEXT NOT NULL,
    cost_crystals INTEGER DEFAULT 0,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Create index on chat_id for messages
CREATE INDEX idx_messages_chat_id ON messages(chat_id);

-- Create media_assets table
CREATE TABLE media_assets (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    file_url TEXT NOT NULL,
    entity_type VARCHAR(100) NOT NULL,
    entity_id UUID NOT NULL
);

-- Create index on entity_type and entity_id for media_assets
CREATE INDEX idx_media_entity ON media_assets(entity_type, entity_id);

-- Insert test users
INSERT INTO users (id, test_username, google_id, crystal_balance) VALUES
    ('550e8400-e29b-41d4-a716-446655440000', 'admin_test', 'admin@google.com', 5000),
    ('550e8400-e29b-41d4-a716-446655440001', 'api_test', 'api@google.com', 3000),
    ('550e8400-e29b-41d4-a716-446655440002', 'dev_test', 'dev@google.com', 1000),
    ('550e8400-e29b-41d4-a716-446655440003', 'user_test', 'user@google.com', 2000);

-- Insert test characters
INSERT INTO characters (id, owner_id, name, system_prompt, is_public) VALUES
    ('660e8400-e29b-41d4-a716-446655440000', '550e8400-e29b-41d4-a716-446655440000', 'Helpful Assistant', 'You are a helpful and friendly AI assistant. Always be polite and provide accurate information.', true),
    ('660e8400-e29b-41d4-a716-446655440001', '550e8400-e29b-41d4-a716-446655440001', 'Code Mentor', 'You are an experienced software engineer who helps developers learn and improve their coding skills. Provide clear explanations and examples.', true),
    ('660e8400-e29b-41d4-a716-446655440002', '550e8400-e29b-41d4-a716-446655440002', 'Creative Writer', 'You are a creative writing assistant who helps users craft engaging stories and narratives. Be imaginative and inspiring.', false),
    ('660e8400-e29b-41d4-a716-446655440003', '550e8400-e29b-41d4-a716-446655440003', 'Math Tutor', 'You are a patient math tutor who explains mathematical concepts clearly and helps students solve problems step by step.', true);

-- Insert test scenes
INSERT INTO scenes (id, owner_id, title, background_prompt) VALUES
    ('770e8400-e29b-41d4-a716-446655440000', '550e8400-e29b-41d4-a716-446655440000', 'Office Environment', 'You are in a modern office setting with computers, whiteboards, and a collaborative atmosphere. The conversation takes place during work hours.'),
    ('770e8400-e29b-41d4-a716-446655440001', '550e8400-e29b-41d4-a716-446655440001', 'Cozy Coffee Shop', 'You are sitting in a warm, cozy coffee shop with soft lighting, the aroma of fresh coffee, and gentle background music. Perfect for casual conversations.'),
    ('770e8400-e29b-41d4-a716-446655440002', '550e8400-e29b-41d4-a716-446655440002', 'Library Study Room', 'You are in a quiet library study room surrounded by books and academic resources. The atmosphere is focused and conducive to learning.'),
    ('770e8400-e29b-41d4-a716-446655440003', '550e8400-e29b-41d4-a716-446655440003', 'Virtual Reality Space', 'You are in a futuristic virtual reality environment where anything is possible. The digital landscape can change based on the conversation.');

-- Insert test chats
INSERT INTO chats (id, user_id, character_id, scene_id, created_at) VALUES
    ('880e8400-e29b-41d4-a716-446655440000', '550e8400-e29b-41d4-a716-446655440000', '660e8400-e29b-41d4-a716-446655440000', '770e8400-e29b-41d4-a716-446655440000', NOW() - INTERVAL '2 days'),
    ('880e8400-e29b-41d4-a716-446655440001', '550e8400-e29b-41d4-a716-446655440001', '660e8400-e29b-41d4-a716-446655440001', '770e8400-e29b-41d4-a716-446655440001', NOW() - INTERVAL '1 day'),
    ('880e8400-e29b-41d4-a716-446655440002', '550e8400-e29b-41d4-a716-446655440002', '660e8400-e29b-41d4-a716-446655440002', '770e8400-e29b-41d4-a716-446655440002', NOW() - INTERVAL '12 hours'),
    ('880e8400-e29b-41d4-a716-446655440003', '550e8400-e29b-41d4-a716-446655440003', '660e8400-e29b-41d4-a716-446655440003', NULL, NOW() - INTERVAL '6 hours');

-- Insert test messages
INSERT INTO messages (id, chat_id, role, content, cost_crystals, created_at) VALUES
    -- Chat 1 messages
    ('990e8400-e29b-41d4-a716-446655440000', '880e8400-e29b-41d4-a716-446655440000', 'user', 'Hello! Can you help me with a project?', 0, NOW() - INTERVAL '2 days'),
    ('990e8400-e29b-41d4-a716-446655440001', '880e8400-e29b-41d4-a716-446655440000', 'model', 'Hello! I would be happy to help you with your project. What kind of project are you working on?', 10, NOW() - INTERVAL '2 days' + INTERVAL '30 seconds'),
    ('990e8400-e29b-41d4-a716-446655440002', '880e8400-e29b-41d4-a716-446655440000', 'user', 'I need to create a web application for managing tasks.', 0, NOW() - INTERVAL '2 days' + INTERVAL '2 minutes'),
    
    -- Chat 2 messages
    ('990e8400-e29b-41d4-a716-446655440003', '880e8400-e29b-41d4-a716-446655440001', 'user', 'Can you explain how recursion works in Python?', 0, NOW() - INTERVAL '1 day'),
    ('990e8400-e29b-41d4-a716-446655440004', '880e8400-e29b-41d4-a716-446655440001', 'model', 'Recursion is a programming technique where a function calls itself. Let me explain with an example...', 15, NOW() - INTERVAL '1 day' + INTERVAL '45 seconds'),
    
    -- Chat 3 messages
    ('990e8400-e29b-41d4-a716-446655440005', '880e8400-e29b-41d4-a716-446655440002', 'user', 'Help me write a short story about space exploration.', 0, NOW() - INTERVAL '12 hours'),
    ('990e8400-e29b-41d4-a716-446655440006', '880e8400-e29b-41d4-a716-446655440002', 'model', 'I would love to help you create an engaging space exploration story! Let us start with the setting...', 20, NOW() - INTERVAL '12 hours' + INTERVAL '1 minute'),
    
    -- Chat 4 messages
    ('990e8400-e29b-41d4-a716-446655440007', '880e8400-e29b-41d4-a716-446655440003', 'user', 'I need help with calculus derivatives.', 0, NOW() - INTERVAL '6 hours'),
    ('990e8400-e29b-41d4-a716-446655440008', '880e8400-e29b-41d4-a716-446655440003', 'model', 'I would be happy to help you with calculus derivatives! What specific topic would you like to focus on?', 12, NOW() - INTERVAL '6 hours' + INTERVAL '20 seconds');

-- Insert test media assets
INSERT INTO media_assets (id, file_url, entity_type, entity_id) VALUES
    ('aa0e8400-e29b-41d4-a716-446655440000', 'https://example.com/avatar1.png', 'character', '660e8400-e29b-41d4-a716-446655440000'),
    ('aa0e8400-e29b-41d4-a716-446655440001', 'https://example.com/avatar2.png', 'character', '660e8400-e29b-41d4-a716-446655440001'),
    ('aa0e8400-e29b-41d4-a716-446655440002', 'https://example.com/scene_bg1.jpg', 'scene', '770e8400-e29b-41d4-a716-446655440000'),
    ('aa0e8400-e29b-41d4-a716-446655440003', 'https://example.com/scene_bg2.jpg', 'scene', '770e8400-e29b-41d4-a716-446655440001'),
    ('aa0e8400-e29b-41d4-a716-446655440004', 'https://example.com/user_profile1.jpg', 'user', '550e8400-e29b-41d4-a716-446655440000'),
    ('aa0e8400-e29b-41d4-a716-446655440005', 'https://example.com/user_profile2.jpg', 'user', '550e8400-e29b-41d4-a716-446655440001');

-- Display summary of inserted data
SELECT 'Database initialization completed successfully!' as status;
SELECT 
    'users' as table_name, 
    COUNT(*) as record_count 
FROM users
UNION ALL
SELECT 'characters', COUNT(*) FROM characters
UNION ALL  
SELECT 'scenes', COUNT(*) FROM scenes
UNION ALL
SELECT 'chats', COUNT(*) FROM chats
UNION ALL
SELECT 'messages', COUNT(*) FROM messages
UNION ALL
SELECT 'media_assets', COUNT(*) FROM media_assets;