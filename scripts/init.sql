-- Database initialization script for scripulya_ai
-- Creates tables and inserts test data

-- Enable UUID generation extension
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- Drop tables if they exist (for clean initialization)
DROP TABLE IF EXISTS media_assets CASCADE;
DROP TABLE IF EXISTS messages CASCADE;
DROP TABLE IF EXISTS chat_settings CASCADE;
DROP TABLE IF EXISTS chats CASCADE;
DROP TABLE IF EXISTS scene_bookmarks CASCADE;
DROP TABLE IF EXISTS character_bookmarks CASCADE;
DROP TABLE IF EXISTS scene_likes CASCADE;
DROP TABLE IF EXISTS character_likes CASCADE;
DROP TABLE IF EXISTS character_scene CASCADE;
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
    title TEXT NOT NULL,
    description TEXT,
    background_prompt TEXT NOT NULL,
    initial_message_text TEXT NOT NULL,
    is_public BOOLEAN NOT NULL DEFAULT false
);

-- Create character_scene junction table for many-to-many relationship
CREATE TABLE character_scene (
    character_id UUID NOT NULL REFERENCES characters(id) ON DELETE CASCADE,
    scene_id UUID NOT NULL REFERENCES scenes(id) ON DELETE CASCADE,
    PRIMARY KEY (character_id, scene_id)
);

-- Like / bookmark junction tables (user <-> character/scene). A row's existence
-- is the signal; the composite PK also makes (re)liking idempotent at insert time.
CREATE TABLE character_likes (
    character_id UUID NOT NULL REFERENCES characters(id) ON DELETE CASCADE,
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    PRIMARY KEY (character_id, user_id)
);
CREATE TABLE scene_likes (
    scene_id UUID NOT NULL REFERENCES scenes(id) ON DELETE CASCADE,
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    PRIMARY KEY (scene_id, user_id)
);
CREATE TABLE character_bookmarks (
    character_id UUID NOT NULL REFERENCES characters(id) ON DELETE CASCADE,
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    PRIMARY KEY (character_id, user_id)
);
CREATE TABLE scene_bookmarks (
    scene_id UUID NOT NULL REFERENCES scenes(id) ON DELETE CASCADE,
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    PRIMARY KEY (scene_id, user_id)
);

-- Create chats table
CREATE TABLE chats (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL,
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    scene_id UUID REFERENCES scenes(id) ON DELETE SET NULL,
    user_character_id UUID REFERENCES characters(id) ON DELETE SET NULL,  -- persona the user plays as in this chat
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Create index on user_id for chats
CREATE INDEX idx_chats_user_id ON chats(user_id);

-- Create index on scene_id for chats
CREATE INDEX idx_chats_scene_id ON chats(scene_id);

-- Create index on user_character_id for chats
CREATE INDEX idx_chats_user_character_id ON chats(user_character_id);

-- Create chat_settings table (1:1 with chats; settings stored as a JSONB blob)
CREATE TABLE chat_settings (
    chat_id UUID PRIMARY KEY REFERENCES chats(id) ON DELETE CASCADE,
    settings JSONB NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Create messages table
CREATE TABLE messages (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    chat_id UUID NOT NULL REFERENCES chats(id) ON DELETE CASCADE,
    role VARCHAR(50) NOT NULL CHECK (role IN ('user', 'model')),
    content TEXT NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'completed' CHECK (status IN ('pending', 'completed', 'failed')),
    cost_crystals INTEGER DEFAULT 0,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Create index on chat_id for messages
CREATE INDEX idx_messages_chat_id ON messages(chat_id);

-- Create media_assets table
-- Images live in MinIO/S3 (object storage). A row either points at a managed
-- object (object_key + bucket, uploaded via the media API) OR at a legacy
-- external URL (file_url). content_type/size_bytes/is_public/owner_id describe
-- the asset; is_public picks the bucket at upload time and gates anonymous read.
CREATE TABLE media_assets (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    object_key TEXT,                                    -- MinIO/S3 object key (NULL for legacy external URLs)
    bucket VARCHAR(63),                                 -- which bucket the object lives in (NULL for legacy)
    file_url TEXT,                                      -- legacy/external absolute URL (NULL for managed uploads)
    content_type VARCHAR(100) NOT NULL DEFAULT 'image/png',
    size_bytes BIGINT NOT NULL DEFAULT 0,
    entity_type VARCHAR(100) NOT NULL,                  -- 'character' | 'scene' | 'user'
    entity_id UUID NOT NULL,
    is_public BOOLEAN NOT NULL DEFAULT false,
    owner_id UUID REFERENCES users(id) ON DELETE SET NULL,  -- uploader (NULL for legacy/seeded rows)
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    CHECK (object_key IS NOT NULL OR file_url IS NOT NULL)
);

-- Create index on entity_type and entity_id for media_assets
CREATE INDEX idx_media_entity ON media_assets(entity_type, entity_id);

-- Insert test users
INSERT INTO users (id, test_username, google_id, crystal_balance) VALUES
    ('00000000-0000-0000-0000-000000000001', 'mobile_test', 'mobile@mobile.net', 1000),
    ('5dbdc924-968a-4c50-94a8-44cdd165e460', 'admin_test', 'admin@google.com', 5000),
    ('f5ac5447-d562-4d7b-91fb-dc4d5bcc4395', 'api_test', 'api@google.com', 3000),
    ('4954ef15-b75b-4f92-b32c-ded5e80ce802', 'dev_test', 'dev@google.com', 1000),
    ('4e50271e-2b64-46e4-b312-580782ea6549', 'user_test', 'user@google.com', 2000),
    ('e5fd1874-a299-4c22-b6b5-af4e00b796a7', 'premium_user', 'premium@google.com', 10000),
    ('c23dc540-a0ba-4d83-ac7b-d0f8eab9d463', 'broke_user', 'broke@google.com', 0),
    ('f3ba11a5-4026-4c16-9aed-061f0d490ade', 'new_user', 'new@google.com', 1000),
    ('7edb0c2c-8dcd-402a-a979-cc7853d9b627', 'test_user_long_name_for_testing', 'longname@google.com', 500),
    ('53c41979-a116-4bb7-8281-57fadfd89a13', 'inactive_user', 'inactive@google.com', 2500);

-- Insert test characters
INSERT INTO characters (id, owner_id, name, system_prompt, is_public) VALUES
    ('43341001-4ea1-4f03-b315-811d3264b6a3', '5dbdc924-968a-4c50-94a8-44cdd165e460', 'Helpful Assistant', 'You are a helpful and friendly AI assistant. Always be polite and provide accurate information.', true),
    ('1a0fca84-996c-43b5-976a-0c676c61dde5', 'f5ac5447-d562-4d7b-91fb-dc4d5bcc4395', 'Code Mentor', 'You are an experienced software engineer who helps developers learn and improve their coding skills. Provide clear explanations and examples.', true),
    ('08f6aff7-e5c6-4e96-b4f7-971e03cb81f8', '4954ef15-b75b-4f92-b32c-ded5e80ce802', 'Creative Writer', 'You are a creative writing assistant who helps users craft engaging stories and narratives. Be imaginative and inspiring.', false),
    ('3a50caae-9f5d-4be3-882b-f17cdc10d0e3', '4e50271e-2b64-46e4-b312-580782ea6549', 'Math Tutor', 'You are a patient math tutor who explains mathematical concepts clearly and helps students solve problems step by step.', true),
    ('117737b7-e183-4aac-9a09-47a45c3d6f58', 'e5fd1874-a299-4c22-b6b5-af4e00b796a7', 'Dr. Sophisticated Character Name With Very Long Title For Testing Purposes', 'You are an extremely detailed and sophisticated AI assistant with extensive knowledge across multiple domains. Your responses should be comprehensive, well-structured, and demonstrate deep understanding of complex topics. Always maintain professional demeanor while being approachable and helpful. You excel in providing thorough explanations with examples and can adapt your communication style to match the user''s level of expertise. This is a very long system prompt designed to test the limits of character creation and storage capabilities.', true),
    ('8ed61d7f-27db-4bef-a583-98a0d703ea66', 'c23dc540-a0ba-4d83-ac7b-d0f8eab9d463', 'Simple Bot', 'Simple.', false),
    ('8abecb4a-8d05-4d24-8fab-31ea776640f2', 'f3ba11a5-4026-4c16-9aed-061f0d490ade', 'Gaming Companion', 'You are an enthusiastic gaming companion who loves discussing video games, strategies, and helping players improve their skills.', true),
    ('84d54c1c-6837-44bf-ad31-26c78729a42c', '7edb0c2c-8dcd-402a-a979-cc7853d9b627', 'Meditation Guide', 'You are a calm and peaceful meditation guide who helps users find inner peace and relaxation through guided practices.', false),
    ('9a6cf9ec-11d7-471b-8678-c8651b8f331f', '53c41979-a116-4bb7-8281-57fadfd89a13', 'Travel Advisor', 'You are a knowledgeable travel advisor with expertise in destinations worldwide. Help users plan amazing trips and adventures.', true);

-- Insert test scenes
INSERT INTO scenes (id, owner_id, title, description, background_prompt, initial_message_text) VALUES
    ('5c194d75-401f-4fa2-808c-7092153135b7', '5dbdc924-968a-4c50-94a8-44cdd165e460', 'E2E Test Scene', 'A test scene specifically for e2e tests', 'This is a test scene for e2e testing purposes.', 'Welcome to the e2e test scene!'),
    ('e971d123-2f76-4022-87e6-79fc372cbbf3', '5dbdc924-968a-4c50-94a8-44cdd165e460', 'Office Environment', 'A professional workspace designed for productive conversations and collaborative work sessions.', 'You are in a modern office setting with computers, whiteboards, and a collaborative atmosphere. The conversation takes place during work hours.', 'Welcome to our professional workspace! I''m here to help you with any business-related questions or collaborative projects. What can I assist you with today?'),
    ('641e5f5d-73ea-4ef0-864c-2cb19f311b11', 'f5ac5447-d562-4d7b-91fb-dc4d5bcc4395', 'Cozy Coffee Shop', 'A warm and inviting café atmosphere perfect for relaxed, informal conversations over coffee.', 'You are sitting in a warm, cozy coffee shop with soft lighting, the aroma of fresh coffee, and gentle background music. Perfect for casual conversations.', 'Welcome to our cozy corner of the coffee shop! The aroma of freshly brewed coffee fills the air. What would you like to chat about while we enjoy this peaceful atmosphere?'),
    ('414e2a88-2376-46bd-bde7-06c7a514e0d4', '4954ef15-b75b-4f92-b32c-ded5e80ce802', 'Library Study Room', 'A quiet academic environment ideal for focused learning and educational discussions.', 'You are in a quiet library study room surrounded by books and academic resources. The atmosphere is focused and conducive to learning.', 'Welcome to our quiet study sanctuary! I''m here to help you explore knowledge and dive deep into learning. What subject would you like to discuss today?'),
    ('7a587ee5-d55f-4d09-9ced-927ecc059ff0', '4e50271e-2b64-46e4-b312-580782ea6549', 'Virtual Reality Space', 'An immersive digital environment where imagination and technology merge for limitless possibilities.', 'You are in a futuristic virtual reality environment where anything is possible. The digital landscape can change based on the conversation.', 'Welcome to the infinite possibilities of virtual reality! Here, we can explore any concept, simulate any scenario, or create anything you can imagine. What digital adventure shall we embark on?'),
    ('f08f390a-1237-4bfa-9e53-6980dbb5aa0d', 'e5fd1874-a299-4c22-b6b5-af4e00b796a7', 'Minimalist Scene', NULL, 'Simple background.', 'Hello.'),
    ('c7e7899e-ac69-4024-a79c-252531920cd2', 'c23dc540-a0ba-4d83-ac7b-d0f8eab9d463', 'Epic Fantasy Adventure Scene With Extremely Long Title That Tests The Maximum Length Limits', 'This is an extremely detailed and comprehensive scene description that goes on for a very long time to test the database storage capabilities and API handling of large text fields. The scene depicts a vast fantasy realm filled with magical creatures, ancient castles, mystical forests, flowing rivers, towering mountains, and endless adventures waiting to be discovered. Heroes from all walks of life gather here to embark on epic quests, forge legendary weapons, learn powerful spells, and create lasting friendships. The atmosphere is rich with magic, wonder, and endless possibilities for storytelling and character development.', 'You find yourself in a breathtaking fantasy realm where magic flows through every blade of grass, every stone, and every breath of wind. Ancient dragons soar overhead, their scales glinting in the eternal twilight. Mystical forests whisper secrets of ages past, while crystal-clear streams carry the songs of woodland spirits. Here, time moves differently, and every choice you make shapes the very fabric of this magical world.', 'Greetings, brave adventurer! You have crossed the mystical threshold into our enchanted realm, where ancient magic still flows through the very air you breathe. The great library of spells awaits your discovery, legendary quests call out for heroes, and mythical creatures seek worthy companions. Your epic journey begins now - what path will you choose to walk in this realm of infinite wonder and boundless adventure?'),
    ('2f263740-29f7-4622-b4ce-fd7ac29d04d5', 'f3ba11a5-4026-4c16-9aed-061f0d490ade', 'Beach Resort Paradise', 'Tropical paradise with white sand beaches, crystal clear waters, and endless sunshine.', 'You are relaxing on a pristine tropical beach with gentle waves lapping at the shore, palm trees swaying in the warm breeze, and the sound of seagulls in the distance.', 'Welcome to paradise! Feel the warm sand between your toes and breathe in the fresh ocean air. This tropical haven is the perfect place to unwind and let your worries drift away with the waves. What brings you to our peaceful shore today?'),
    ('5277db85-10c6-4f12-ab23-810f289ca6df', '7edb0c2c-8dcd-402a-a979-cc7853d9b627', 'Space Station Alpha', 'Advanced space station orbiting Earth with cutting-edge technology and stunning views.', 'You are aboard a sophisticated space station with panoramic views of Earth below, advanced control systems, and the vastness of space surrounding you.', 'Welcome aboard Space Station Alpha! From our orbital vantage point, Earth appears as a beautiful blue marble suspended in the cosmic void. Our advanced systems are at your disposal for any space-related inquiries or cosmic conversations. What aspects of space exploration interest you most?'),
    ('e1daa2c4-3c0b-4ac5-9937-c9540f80c85e', '53c41979-a116-4bb7-8281-57fadfd89a13', 'Underground Laboratory', 'Secret research facility beneath the city for conducting advanced experiments.', 'You are in a high-tech underground laboratory filled with mysterious equipment, glowing screens, and the hum of advanced machinery.', 'Welcome to Laboratory Complex Omega! You''ve gained access to our most advanced research facility. The equipment around us represents the cutting edge of scientific innovation. What experiments or research topics would you like to explore in our secure environment?');

-- Mark a few seeded scenes public (the rest stay private via the column default)
UPDATE scenes SET is_public = true WHERE title IN ('Cozy Coffee Shop', 'Beach Resort Paradise', 'Space Station Alpha');

-- Insert test character_scene associations
INSERT INTO character_scene (character_id, scene_id) VALUES
    -- Helpful Assistant works well in office and coffee shop environments
    ('43341001-4ea1-4f03-b315-811d3264b6a3', 'e971d123-2f76-4022-87e6-79fc372cbbf3'), -- Helpful Assistant + Office Environment
    ('43341001-4ea1-4f03-b315-811d3264b6a3', '641e5f5d-73ea-4ef0-864c-2cb19f311b11'), -- Helpful Assistant + Cozy Coffee Shop
    ('43341001-4ea1-4f03-b315-811d3264b6a3', '2f263740-29f7-4622-b4ce-fd7ac29d04d5'), -- Helpful Assistant + Beach Resort
    
    -- Code Mentor is perfect for office and virtual reality environments
    ('1a0fca84-996c-43b5-976a-0c676c61dde5', 'e971d123-2f76-4022-87e6-79fc372cbbf3'), -- Code Mentor + Office Environment
    ('1a0fca84-996c-43b5-976a-0c676c61dde5', '7a587ee5-d55f-4d09-9ced-927ecc059ff0'), -- Code Mentor + Virtual Reality Space
    ('1a0fca84-996c-43b5-976a-0c676c61dde5', 'e1daa2c4-3c0b-4ac5-9937-c9540f80c85e'), -- Code Mentor + Underground Lab
    
    -- Creative Writer thrives in coffee shop and virtual reality spaces
    ('08f6aff7-e5c6-4e96-b4f7-971e03cb81f8', '641e5f5d-73ea-4ef0-864c-2cb19f311b11'), -- Creative Writer + Cozy Coffee Shop
    ('08f6aff7-e5c6-4e96-b4f7-971e03cb81f8', '7a587ee5-d55f-4d09-9ced-927ecc059ff0'), -- Creative Writer + Virtual Reality Space
    ('08f6aff7-e5c6-4e96-b4f7-971e03cb81f8', 'c7e7899e-ac69-4024-a79c-252531920cd2'), -- Creative Writer + Epic Fantasy
    
    -- Math Tutor is ideal for library and office environments
    ('3a50caae-9f5d-4be3-882b-f17cdc10d0e3', '414e2a88-2376-46bd-bde7-06c7a514e0d4'), -- Math Tutor + Library Study Room
    ('3a50caae-9f5d-4be3-882b-f17cdc10d0e3', 'e971d123-2f76-4022-87e6-79fc372cbbf3'), -- Math Tutor + Office Environment
    
    -- Dr. Sophisticated works in multiple environments
    ('117737b7-e183-4aac-9a09-47a45c3d6f58', '414e2a88-2376-46bd-bde7-06c7a514e0d4'), -- Dr. Sophisticated + Library
    ('117737b7-e183-4aac-9a09-47a45c3d6f58', '5277db85-10c6-4f12-ab23-810f289ca6df'), -- Dr. Sophisticated + Space Station
    ('117737b7-e183-4aac-9a09-47a45c3d6f58', 'e1daa2c4-3c0b-4ac5-9937-c9540f80c85e'), -- Dr. Sophisticated + Underground Lab
    
    -- Simple Bot in minimal environments
    ('8ed61d7f-27db-4bef-a583-98a0d703ea66', 'f08f390a-1237-4bfa-9e53-6980dbb5aa0d'), -- Simple Bot + Minimalist Scene
    
    -- Gaming Companion in virtual and fantasy environments
    ('8abecb4a-8d05-4d24-8fab-31ea776640f2', '7a587ee5-d55f-4d09-9ced-927ecc059ff0'), -- Gaming Companion + Virtual Reality
    ('8abecb4a-8d05-4d24-8fab-31ea776640f2', 'c7e7899e-ac69-4024-a79c-252531920cd2'), -- Gaming Companion + Epic Fantasy
    ('8abecb4a-8d05-4d24-8fab-31ea776640f2', '5277db85-10c6-4f12-ab23-810f289ca6df'), -- Gaming Companion + Space Station
    
    -- Meditation Guide in peaceful environments
    ('84d54c1c-6837-44bf-ad31-26c78729a42c', '2f263740-29f7-4622-b4ce-fd7ac29d04d5'), -- Meditation Guide + Beach Resort
    ('84d54c1c-6837-44bf-ad31-26c78729a42c', 'f08f390a-1237-4bfa-9e53-6980dbb5aa0d'), -- Meditation Guide + Minimalist Scene
    
    -- Travel Advisor in diverse locations
    ('9a6cf9ec-11d7-471b-8678-c8651b8f331f', '2f263740-29f7-4622-b4ce-fd7ac29d04d5'), -- Travel Advisor + Beach Resort
    ('9a6cf9ec-11d7-471b-8678-c8651b8f331f', '5277db85-10c6-4f12-ab23-810f289ca6df'), -- Travel Advisor + Space Station
    ('9a6cf9ec-11d7-471b-8678-c8651b8f331f', '641e5f5d-73ea-4ef0-864c-2cb19f311b11'); -- Travel Advisor + Coffee Shop

-- Insert test chats
INSERT INTO chats (id, name, user_id, scene_id, created_at) VALUES
    ('82dc4309-0ab2-4a9d-86c9-a49f8931494a', 'E2E Test Chat', '5dbdc924-968a-4c50-94a8-44cdd165e460', '5c194d75-401f-4fa2-808c-7092153135b7', NOW()),
    ('048a7fe5-f4c2-40ef-9745-7d85d7c4c5fb', 'Project Help Chat', '5dbdc924-968a-4c50-94a8-44cdd165e460', 'e971d123-2f76-4022-87e6-79fc372cbbf3', NOW() - INTERVAL '2 days'),
    ('90d27426-7b7a-4a4d-ba17-6f98b7c29c5e', 'Python Recursion Chat', 'f5ac5447-d562-4d7b-91fb-dc4d5bcc4395', '641e5f5d-73ea-4ef0-864c-2cb19f311b11', NOW() - INTERVAL '1 day'),
    ('d99678f7-bb8c-41f4-9726-4722b44a5649', 'Space Story Writing', '4954ef15-b75b-4f92-b32c-ded5e80ce802', '414e2a88-2376-46bd-bde7-06c7a514e0d4', NOW() - INTERVAL '12 hours'),
    ('ad8b09b7-1723-4459-ba61-5bf3a2699c11', 'Calculus Help', '4e50271e-2b64-46e4-b312-580782ea6549', '414e2a88-2376-46bd-bde7-06c7a514e0d4', NOW() - INTERVAL '6 hours'),
    ('4bf7237c-ad71-4bb7-a9d9-27ae911bc1b8', 'Fantasy ML Discussion', 'e5fd1874-a299-4c22-b6b5-af4e00b796a7', 'c7e7899e-ac69-4024-a79c-252531920cd2', NOW() - INTERVAL '3 hours'),
    ('14555316-cbfc-4254-85b5-e737863edc18', 'Simple Chat', 'c23dc540-a0ba-4d83-ac7b-d0f8eab9d463', 'f08f390a-1237-4bfa-9e53-6980dbb5aa0d', NOW() - INTERVAL '1 hour'),
    ('7eec932a-1730-48a3-b547-d4c67161bf18', 'RPG Strategy Chat', 'f3ba11a5-4026-4c16-9aed-061f0d490ade', '7a587ee5-d55f-4d09-9ced-927ecc059ff0', NOW() - INTERVAL '30 minutes'),
    ('0469588e-75f8-487f-8ce1-4434be8513c0', 'Stress Relief Session', '7edb0c2c-8dcd-402a-a979-cc7853d9b627', '2f263740-29f7-4622-b4ce-fd7ac29d04d5', NOW() - INTERVAL '15 minutes'),
    ('0d19dc52-a72a-4ae6-840f-04b55858a231', 'Space Travel Planning', '53c41979-a116-4bb7-8281-57fadfd89a13', '5277db85-10c6-4f12-ab23-810f289ca6df', NOW() - INTERVAL '5 minutes'),
    ('8a32d249-137b-4f8c-95c8-1665f7b0b9fb', 'Mars Mission Chat', '5dbdc924-968a-4c50-94a8-44cdd165e460', '5277db85-10c6-4f12-ab23-810f289ca6df', NOW() - INTERVAL '7 days'),
    ('3b0ea7ee-d883-49d9-aabd-5cf497c6db79', 'Quantum Computing Analysis', 'f5ac5447-d562-4d7b-91fb-dc4d5bcc4395', 'e1daa2c4-3c0b-4ac5-9937-c9540f80c85e', NOW() - INTERVAL '10 days');

-- Seed a chat with a user persona (the character the user plays as in that chat)
UPDATE chats SET user_character_id = '43341001-4ea1-4f03-b315-811d3264b6a3'  -- Helpful Assistant, owned by admin_test
WHERE id = '048a7fe5-f4c2-40ef-9745-7d85d7c4c5fb';  -- Project Help Chat

-- The E2E test chat also needs a persona: message e2e tests send into it, and a
-- play-as character is required to play a story.
UPDATE chats SET user_character_id = '43341001-4ea1-4f03-b315-811d3264b6a3'
WHERE id = '82dc4309-0ab2-4a9d-86c9-a49f8931494a';  -- E2E Test Chat

-- Insert test messages
INSERT INTO messages (id, chat_id, role, content, cost_crystals, created_at) VALUES
    -- Chat 1 messages
    ('f7023ee5-06e3-476a-bb12-1e43122578ad', '048a7fe5-f4c2-40ef-9745-7d85d7c4c5fb', 'user', 'Hello! Can you help me with a project?', 0, NOW() - INTERVAL '2 days'),
    ('53eff80a-2469-43f1-92de-95f48d1486cf', '048a7fe5-f4c2-40ef-9745-7d85d7c4c5fb', 'model', 'Hello! I would be happy to help you with your project. What kind of project are you working on?', 10, NOW() - INTERVAL '2 days' + INTERVAL '30 seconds'),
    ('ae16fdd3-1d7d-45ee-bb7a-b9efe8147250', '048a7fe5-f4c2-40ef-9745-7d85d7c4c5fb', 'user', 'I need to create a web application for managing tasks.', 0, NOW() - INTERVAL '2 days' + INTERVAL '2 minutes'),
    
    -- Chat 2 messages
    ('3bb87e98-9d32-4a51-9176-6c32345ad770', '90d27426-7b7a-4a4d-ba17-6f98b7c29c5e', 'user', 'Can you explain how recursion works in Python?', 0, NOW() - INTERVAL '1 day'),
    ('3d820ed4-bec8-425f-960c-cfcc2973eeae', '90d27426-7b7a-4a4d-ba17-6f98b7c29c5e', 'model', 'Recursion is a programming technique where a function calls itself. Let me explain with an example...', 15, NOW() - INTERVAL '1 day' + INTERVAL '45 seconds'),
    
    -- Chat 3 messages
    ('3f733ab8-4728-496f-b50e-61accf472991', 'd99678f7-bb8c-41f4-9726-4722b44a5649', 'user', 'Help me write a short story about space exploration.', 0, NOW() - INTERVAL '12 hours'),
    ('933339b6-f813-4719-a1f1-45d680359896', 'd99678f7-bb8c-41f4-9726-4722b44a5649', 'model', 'I would love to help you create an engaging space exploration story! Let us start with the setting...', 20, NOW() - INTERVAL '12 hours' + INTERVAL '1 minute'),
    
    -- Chat 4 messages
    ('527dd306-b878-4fae-806e-5158110f90d7', 'ad8b09b7-1723-4459-ba61-5bf3a2699c11', 'user', 'I need help with calculus derivatives.', 0, NOW() - INTERVAL '6 hours'),
    ('7f0135b7-270b-4a48-be1d-56a54390737e', 'ad8b09b7-1723-4459-ba61-5bf3a2699c11', 'model', 'I would be happy to help you with calculus derivatives! What specific topic would you like to focus on?', 12, NOW() - INTERVAL '6 hours' + INTERVAL '20 seconds'),
    
    -- Chat 5 messages (Dr. Sophisticated)
    ('8f697477-7ee1-4d42-8081-4e2bf956cae1', '4bf7237c-ad71-4bb7-a9d9-27ae911bc1b8', 'model', 'Welcome to the Epic Fantasy Adventure Scene. Your conversation will be enhanced by magical elements and rich storytelling.', 0, NOW() - INTERVAL '3 hours'),
    ('f6b44e8b-4201-403f-b71d-e08623e2c2da', '4bf7237c-ad71-4bb7-a9d9-27ae911bc1b8', 'user', 'Tell me about advanced machine learning techniques.', 0, NOW() - INTERVAL '3 hours' + INTERVAL '1 minute'),
    ('763b3bed-ae73-4b90-8781-d152f729fa29', '4bf7237c-ad71-4bb7-a9d9-27ae911bc1b8', 'model', 'Greetings! I shall illuminate the magnificent realm of advanced machine learning for you. In this magical domain of artificial intelligence, we encounter sophisticated techniques such as deep neural networks, transformer architectures, and reinforcement learning algorithms. These powerful methodologies represent the cutting edge of computational intelligence, capable of solving complex problems that were once thought impossible. Allow me to elaborate on each of these fascinating approaches...', 50, NOW() - INTERVAL '3 hours' + INTERVAL '2 minutes'),
    
    -- Chat 6 messages (Simple Bot)
    ('b383cef2-e5e0-491c-8aa4-97521fbcd44f', '14555316-cbfc-4254-85b5-e737863edc18', 'user', 'Hi', 0, NOW() - INTERVAL '1 hour'),
    ('cba20f48-2544-4bbf-a401-b7f841d95bd7', '14555316-cbfc-4254-85b5-e737863edc18', 'model', 'Hi.', 1, NOW() - INTERVAL '1 hour' + INTERVAL '5 seconds'),
    
    -- Chat 7 messages (Gaming Companion)
    ('74f8172e-95e9-47ce-bdde-366fedadf23f', '7eec932a-1730-48a3-b547-d4c67161bf18', 'user', 'What are the best strategies for playing RPGs?', 0, NOW() - INTERVAL '30 minutes'),
    ('62c93a1d-9c40-4a23-b607-f159cb3dcb8d', '7eec932a-1730-48a3-b547-d4c67161bf18', 'model', 'Great question! RPG strategies depend on the game type, but here are some universal tips...', 25, NOW() - INTERVAL '30 minutes' + INTERVAL '30 seconds'),
    
    -- Chat 8 messages (Meditation Guide)
    ('01e52043-b4c7-4011-b4fc-b82dc2ee4b09', '0469588e-75f8-487f-8ce1-4434be8513c0', 'user', 'I am feeling stressed. Can you help me relax?', 0, NOW() - INTERVAL '15 minutes'),
    ('96891009-0015-4849-8b46-2a1f4a3bcc8b', '0469588e-75f8-487f-8ce1-4434be8513c0', 'model', 'Of course. Let us begin with some deep breathing exercises. Find a comfortable position...', 18, NOW() - INTERVAL '15 minutes' + INTERVAL '45 seconds'),
    
    -- Chat 9 messages (Travel Advisor)
    ('f3014238-e372-4b00-8cd6-973f67aec537', '0d19dc52-a72a-4ae6-840f-04b55858a231', 'user', 'What destinations would you recommend for a space travel enthusiast?', 0, NOW() - INTERVAL '5 minutes'),
    ('002629c1-ccd5-42d2-bed8-1ebd61177077', '0d19dc52-a72a-4ae6-840f-04b55858a231', 'model', 'For space enthusiasts, I highly recommend visiting Kennedy Space Center in Florida, NASA Johnson Space Center in Houston, and the Griffith Observatory in Los Angeles for stunning astronomical views.', 35, NOW() - INTERVAL '5 minutes' + INTERVAL '1 minute'),
    
    -- Chat 10 messages (Long conversation)
    ('0a2d8794-bca6-4b21-ab85-ebf0c740b3a3', '8a32d249-137b-4f8c-95c8-1665f7b0b9fb', 'model', 'This is a system message to initialize the space station environment for enhanced conversation context.', 0, NOW() - INTERVAL '7 days'),
    ('b0e86dd8-4450-46ba-8130-d26cc48098f2', '8a32d249-137b-4f8c-95c8-1665f7b0b9fb', 'user', 'How do you plan a trip to Mars?', 0, NOW() - INTERVAL '7 days' + INTERVAL '2 minutes'),
    ('da651db6-8d7c-4072-8aed-3e72ca1a4feb', '8a32d249-137b-4f8c-95c8-1665f7b0b9fb', 'model', 'Planning a trip to Mars involves numerous complex considerations including launch windows, spacecraft design, life support systems, radiation protection, and mission duration. Current estimates suggest a journey would take 6-9 months each way.', 100, NOW() - INTERVAL '7 days' + INTERVAL '3 minutes'),
    ('13f24044-fa13-4312-b43b-20e7f3b31dee', '8a32d249-137b-4f8c-95c8-1665f7b0b9fb', 'user', 'What about the psychological challenges?', 0, NOW() - INTERVAL '7 days' + INTERVAL '5 minutes'),
    ('eb8a1b62-dc81-435e-83aa-7c7f9a9e7c30', '8a32d249-137b-4f8c-95c8-1665f7b0b9fb', 'model', 'Excellent question! The psychological challenges are immense - isolation, confinement, communication delays with Earth, and the stress of knowing you cannot return quickly. Astronauts would need extensive mental health support.', 75, NOW() - INTERVAL '7 days' + INTERVAL '6 minutes'),
    
    -- Chat 11 messages (High cost conversation)
    ('d92f7708-57e3-409a-bad1-1fe883afe1f4', '3b0ea7ee-d883-49d9-aabd-5cf497c6db79', 'user', 'Write me a detailed analysis of quantum computing.', 0, NOW() - INTERVAL '10 days'),
    ('6aa69681-627e-440c-ab60-3667e2d36da9', '3b0ea7ee-d883-49d9-aabd-5cf497c6db79', 'model', 'Quantum computing represents a revolutionary paradigm in computational science, leveraging the principles of quantum mechanics to process information in fundamentally different ways than classical computers. This technology promises exponential speedups for certain types of problems...', 150, NOW() - INTERVAL '10 days' + INTERVAL '2 minutes');

-- Align edited timestamps with creation time for seeded messages (not edited yet)
UPDATE messages SET updated_at = created_at;

-- Insert test media assets
-- Legacy / external assets for characters and users (object_key IS NULL). The bulk
-- UPDATE below marks these public so GET /api/v1/media/{id} returns file_url as-is.
INSERT INTO media_assets (id, file_url, entity_type, entity_id) VALUES
    ('fc8a47d7-010a-48f1-8be4-a711760c547f', 'https://example.com/avatar1.png', 'character', '43341001-4ea1-4f03-b315-811d3264b6a3'),
    ('c9709cfb-f8bc-4744-99bf-f4273b01f0dc', 'https://example.com/avatar2.png', 'character', '1a0fca84-996c-43b5-976a-0c676c61dde5'),
    ('8961b230-0504-4540-bb4c-540551cf2bdf', 'https://example.com/user_profile1.jpg', 'user', '5dbdc924-968a-4c50-94a8-44cdd165e460'),
    ('4fdf4deb-1e61-4e22-8c29-77514fab0f83', 'https://example.com/user_profile2.jpg', 'user', 'f5ac5447-d562-4d7b-91fb-dc4d5bcc4395'),
    ('886e8915-2492-4faa-8c57-9fa3ec5dd37b', 'https://cdn.amazonaws.com/storage/characters/sophisticated-character-avatar-high-resolution.png', 'character', '117737b7-e183-4aac-9a09-47a45c3d6f58'),
    ('fa0c662f-a84c-4862-ad38-643816925d1a', 'https://example.com/simple.gif', 'character', '8ed61d7f-27db-4bef-a583-98a0d703ea66'),
    ('5dcbfb55-ceab-4ddc-889c-ab646576ebcd', 'https://gaming-assets.s3.amazonaws.com/avatars/gaming_companion_animated.webp', 'character', '8abecb4a-8d05-4d24-8fab-31ea776640f2'),
    ('a2c3f558-2939-4502-9fc5-2a4551599e87', 'https://meditation-images.cloudfront.net/peaceful-guide-portrait.svg', 'character', '84d54c1c-6837-44bf-ad31-26c78729a42c'),
    ('4a077616-4dc5-4b70-8145-fc7fce723813', 'https://travel-media.example.org/advisor-profile-hd.jpeg', 'character', '9a6cf9ec-11d7-471b-8678-c8651b8f331f'),
    ('26e7e583-63eb-4069-b6c3-f9c93e3b9708', 'https://user-profiles.example.com/premium-user-badge.ico', 'user', 'e5fd1874-a299-4c22-b6b5-af4e00b796a7'),
    ('449b8ea2-f9d6-4c88-a70b-63d832f2436a', 'https://example.com/default-avatar.svg', 'user', 'c23dc540-a0ba-4d83-ac7b-d0f8eab9d463'),
    ('bcfb901c-84c9-4236-8c9f-d7d6fee7805e', 'https://profile-images.example.net/new-user-welcome-banner.webp', 'user', 'f3ba11a5-4026-4c16-9aed-061f0d490ade'),
    ('8212d164-1600-4aea-936e-16ce861eb58b', 'https://very-long-domain-name-for-testing-purposes.example.organization/extremely/long/path/structure/for/testing/url/length/limits/user-profile-image-with-very-descriptive-filename.jpg', 'user', '7edb0c2c-8dcd-402a-a979-cc7853d9b627'),
    ('34e2a21b-d1cd-4cb9-9f30-f1cee4703868', 'https://inactive-user-assets.example.com/placeholder.png', 'user', '53c41979-a116-4bb7-8281-57fadfd89a13');

-- Scene backgrounds: managed objects in MinIO (scripulya-public), generated and
-- uploaded by the minio-init seed sidecar in scripulya_deploy from each scene's
-- background_prompt via an image model. object_key is the single source of truth the
-- sidecar uploads to (see scripts/seed_minio_media.py). size_bytes is back-filled by
-- the sidecar after upload; the read path only needs object_key+bucket+is_public.
INSERT INTO media_assets (id, object_key, bucket, content_type, entity_type, entity_id, is_public) VALUES
    ('1c93f02d-e19a-4304-9eaa-bcf9edc6d24f', 'scene/e2e-test.png',         'scripulya-public', 'image/png', 'scene', '5c194d75-401f-4fa2-808c-7092153135b7', true), -- E2E Test Scene
    ('726e284c-d65b-4817-bc73-d654db2854b0', 'scene/office.png',           'scripulya-public', 'image/png', 'scene', 'e971d123-2f76-4022-87e6-79fc372cbbf3', true), -- Office Environment
    ('e29d17cf-0769-40f1-92b5-7a3d45683cfa', 'scene/coffee-shop.png',      'scripulya-public', 'image/png', 'scene', '641e5f5d-73ea-4ef0-864c-2cb19f311b11', true), -- Cozy Coffee Shop
    ('a08ff485-b567-4c2f-bb00-7f98ef566401', 'scene/library.png',          'scripulya-public', 'image/png', 'scene', '414e2a88-2376-46bd-bde7-06c7a514e0d4', true), -- Library Study Room
    ('cbcf5eb0-9a9c-4628-abf5-291e5fe4d086', 'scene/vr-space.png',         'scripulya-public', 'image/png', 'scene', '7a587ee5-d55f-4d09-9ced-927ecc059ff0', true), -- Virtual Reality Space
    ('05591567-becb-447f-9070-b0d4db85f307', 'scene/minimalist.png',       'scripulya-public', 'image/png', 'scene', 'f08f390a-1237-4bfa-9e53-6980dbb5aa0d', true), -- Minimalist Scene
    ('0c355303-4715-4d94-86a4-5edb450ff93a', 'scene/fantasy.png',          'scripulya-public', 'image/png', 'scene', 'c7e7899e-ac69-4024-a79c-252531920cd2', true), -- Epic Fantasy Adventure
    ('ad1b4f32-b181-4a79-9627-09d2ba9ca79c', 'scene/beach.png',            'scripulya-public', 'image/png', 'scene', '2f263740-29f7-4622-b4ce-fd7ac29d04d5', true), -- Beach Resort Paradise
    ('bca058ca-e53d-47a4-9145-501510142c29', 'scene/space-station.png',    'scripulya-public', 'image/png', 'scene', '5277db85-10c6-4f12-ab23-810f289ca6df', true), -- Space Station Alpha
    ('febfb826-a578-43ab-858d-0c8060699e77', 'scene/underground-lab.png',  'scripulya-public', 'image/png', 'scene', 'e1daa2c4-3c0b-4ac5-9937-c9540f80c85e', true); -- Underground Laboratory

-- All legacy rows use an external file_url (object_key IS NULL): treat them as public
-- so the read path (GET /api/v1/media/{id}) returns the URL as-is. Managed scene rows
-- above carry their own object_key + is_public and are left untouched here.
UPDATE media_assets SET is_public = true WHERE object_key IS NULL;

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
SELECT 'character_scene', COUNT(*) FROM character_scene
UNION ALL
SELECT 'character_likes', COUNT(*) FROM character_likes
UNION ALL
SELECT 'scene_likes', COUNT(*) FROM scene_likes
UNION ALL
SELECT 'character_bookmarks', COUNT(*) FROM character_bookmarks
UNION ALL
SELECT 'scene_bookmarks', COUNT(*) FROM scene_bookmarks
UNION ALL
SELECT 'chats', COUNT(*) FROM chats
UNION ALL
SELECT 'messages', COUNT(*) FROM messages
UNION ALL
SELECT 'media_assets', COUNT(*) FROM media_assets;