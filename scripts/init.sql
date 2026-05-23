-- Database initialization script for scripulya_ai
-- Creates tables and inserts test data

-- Enable UUID generation extension
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- Drop tables if they exist (for clean initialization)
DROP TABLE IF EXISTS media_assets CASCADE;
DROP TABLE IF EXISTS messages CASCADE;
DROP TABLE IF EXISTS chats CASCADE;
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
    initial_message_text TEXT NOT NULL
);

-- Create character_scene junction table for many-to-many relationship
CREATE TABLE character_scene (
    character_id UUID NOT NULL REFERENCES characters(id) ON DELETE CASCADE,
    scene_id UUID NOT NULL REFERENCES scenes(id) ON DELETE CASCADE,
    PRIMARY KEY (character_id, scene_id)
);

-- Create chats table
CREATE TABLE chats (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL,
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    scene_id UUID REFERENCES scenes(id) ON DELETE SET NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Create index on user_id for chats
CREATE INDEX idx_chats_user_id ON chats(user_id);

-- Create messages table
CREATE TABLE messages (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    chat_id UUID NOT NULL REFERENCES chats(id) ON DELETE CASCADE,
    role VARCHAR(50) NOT NULL CHECK (role IN ('user', 'model')),
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
    ('550e8400-e29b-41d4-a716-446655440003', 'user_test', 'user@google.com', 2000),
    ('550e8400-e29b-41d4-a716-446655440004', 'premium_user', 'premium@google.com', 10000),
    ('550e8400-e29b-41d4-a716-446655440005', 'broke_user', 'broke@google.com', 0),
    ('550e8400-e29b-41d4-a716-446655440006', 'new_user', 'new@google.com', 1000),
    ('550e8400-e29b-41d4-a716-446655440007', 'test_user_long_name_for_testing', 'longname@google.com', 500),
    ('550e8400-e29b-41d4-a716-446655440008', 'inactive_user', 'inactive@google.com', 2500);

-- Insert test characters
INSERT INTO characters (id, owner_id, name, system_prompt, is_public) VALUES
    ('660e8400-e29b-41d4-a716-446655440000', '550e8400-e29b-41d4-a716-446655440000', 'Helpful Assistant', 'You are a helpful and friendly AI assistant. Always be polite and provide accurate information.', true),
    ('660e8400-e29b-41d4-a716-446655440001', '550e8400-e29b-41d4-a716-446655440001', 'Code Mentor', 'You are an experienced software engineer who helps developers learn and improve their coding skills. Provide clear explanations and examples.', true),
    ('660e8400-e29b-41d4-a716-446655440002', '550e8400-e29b-41d4-a716-446655440002', 'Creative Writer', 'You are a creative writing assistant who helps users craft engaging stories and narratives. Be imaginative and inspiring.', false),
    ('660e8400-e29b-41d4-a716-446655440003', '550e8400-e29b-41d4-a716-446655440003', 'Math Tutor', 'You are a patient math tutor who explains mathematical concepts clearly and helps students solve problems step by step.', true),
    ('660e8400-e29b-41d4-a716-446655440004', '550e8400-e29b-41d4-a716-446655440004', 'Dr. Sophisticated Character Name With Very Long Title For Testing Purposes', 'You are an extremely detailed and sophisticated AI assistant with extensive knowledge across multiple domains. Your responses should be comprehensive, well-structured, and demonstrate deep understanding of complex topics. Always maintain professional demeanor while being approachable and helpful. You excel in providing thorough explanations with examples and can adapt your communication style to match the user''s level of expertise. This is a very long system prompt designed to test the limits of character creation and storage capabilities.', true),
    ('660e8400-e29b-41d4-a716-446655440005', '550e8400-e29b-41d4-a716-446655440005', 'Simple Bot', 'Simple.', false),
    ('660e8400-e29b-41d4-a716-446655440006', '550e8400-e29b-41d4-a716-446655440006', 'Gaming Companion', 'You are an enthusiastic gaming companion who loves discussing video games, strategies, and helping players improve their skills.', true),
    ('660e8400-e29b-41d4-a716-446655440007', '550e8400-e29b-41d4-a716-446655440007', 'Meditation Guide', 'You are a calm and peaceful meditation guide who helps users find inner peace and relaxation through guided practices.', false),
    ('660e8400-e29b-41d4-a716-446655440008', '550e8400-e29b-41d4-a716-446655440008', 'Travel Advisor', 'You are a knowledgeable travel advisor with expertise in destinations worldwide. Help users plan amazing trips and adventures.', true);

-- Insert test scenes
INSERT INTO scenes (id, owner_id, title, description, background_prompt, initial_message_text) VALUES
    ('550e8400-e29b-41d4-a716-446655440001', '550e8400-e29b-41d4-a716-446655440000', 'E2E Test Scene', 'A test scene specifically for e2e tests', 'This is a test scene for e2e testing purposes.', 'Welcome to the e2e test scene!'),
    ('770e8400-e29b-41d4-a716-446655440000', '550e8400-e29b-41d4-a716-446655440000', 'Office Environment', 'A professional workspace designed for productive conversations and collaborative work sessions.', 'You are in a modern office setting with computers, whiteboards, and a collaborative atmosphere. The conversation takes place during work hours.', 'Welcome to our professional workspace! I''m here to help you with any business-related questions or collaborative projects. What can I assist you with today?'),
    ('770e8400-e29b-41d4-a716-446655440001', '550e8400-e29b-41d4-a716-446655440001', 'Cozy Coffee Shop', 'A warm and inviting café atmosphere perfect for relaxed, informal conversations over coffee.', 'You are sitting in a warm, cozy coffee shop with soft lighting, the aroma of fresh coffee, and gentle background music. Perfect for casual conversations.', 'Welcome to our cozy corner of the coffee shop! The aroma of freshly brewed coffee fills the air. What would you like to chat about while we enjoy this peaceful atmosphere?'),
    ('770e8400-e29b-41d4-a716-446655440002', '550e8400-e29b-41d4-a716-446655440002', 'Library Study Room', 'A quiet academic environment ideal for focused learning and educational discussions.', 'You are in a quiet library study room surrounded by books and academic resources. The atmosphere is focused and conducive to learning.', 'Welcome to our quiet study sanctuary! I''m here to help you explore knowledge and dive deep into learning. What subject would you like to discuss today?'),
    ('770e8400-e29b-41d4-a716-446655440003', '550e8400-e29b-41d4-a716-446655440003', 'Virtual Reality Space', 'An immersive digital environment where imagination and technology merge for limitless possibilities.', 'You are in a futuristic virtual reality environment where anything is possible. The digital landscape can change based on the conversation.', 'Welcome to the infinite possibilities of virtual reality! Here, we can explore any concept, simulate any scenario, or create anything you can imagine. What digital adventure shall we embark on?'),
    ('770e8400-e29b-41d4-a716-446655440004', '550e8400-e29b-41d4-a716-446655440004', 'Minimalist Scene', NULL, 'Simple background.', 'Hello.'),
    ('770e8400-e29b-41d4-a716-446655440005', '550e8400-e29b-41d4-a716-446655440005', 'Epic Fantasy Adventure Scene With Extremely Long Title That Tests The Maximum Length Limits', 'This is an extremely detailed and comprehensive scene description that goes on for a very long time to test the database storage capabilities and API handling of large text fields. The scene depicts a vast fantasy realm filled with magical creatures, ancient castles, mystical forests, flowing rivers, towering mountains, and endless adventures waiting to be discovered. Heroes from all walks of life gather here to embark on epic quests, forge legendary weapons, learn powerful spells, and create lasting friendships. The atmosphere is rich with magic, wonder, and endless possibilities for storytelling and character development.', 'You find yourself in a breathtaking fantasy realm where magic flows through every blade of grass, every stone, and every breath of wind. Ancient dragons soar overhead, their scales glinting in the eternal twilight. Mystical forests whisper secrets of ages past, while crystal-clear streams carry the songs of woodland spirits. Here, time moves differently, and every choice you make shapes the very fabric of this magical world.', 'Greetings, brave adventurer! You have crossed the mystical threshold into our enchanted realm, where ancient magic still flows through the very air you breathe. The great library of spells awaits your discovery, legendary quests call out for heroes, and mythical creatures seek worthy companions. Your epic journey begins now - what path will you choose to walk in this realm of infinite wonder and boundless adventure?'),
    ('770e8400-e29b-41d4-a716-446655440006', '550e8400-e29b-41d4-a716-446655440006', 'Beach Resort Paradise', 'Tropical paradise with white sand beaches, crystal clear waters, and endless sunshine.', 'You are relaxing on a pristine tropical beach with gentle waves lapping at the shore, palm trees swaying in the warm breeze, and the sound of seagulls in the distance.', 'Welcome to paradise! Feel the warm sand between your toes and breathe in the fresh ocean air. This tropical haven is the perfect place to unwind and let your worries drift away with the waves. What brings you to our peaceful shore today?'),
    ('770e8400-e29b-41d4-a716-446655440007', '550e8400-e29b-41d4-a716-446655440007', 'Space Station Alpha', 'Advanced space station orbiting Earth with cutting-edge technology and stunning views.', 'You are aboard a sophisticated space station with panoramic views of Earth below, advanced control systems, and the vastness of space surrounding you.', 'Welcome aboard Space Station Alpha! From our orbital vantage point, Earth appears as a beautiful blue marble suspended in the cosmic void. Our advanced systems are at your disposal for any space-related inquiries or cosmic conversations. What aspects of space exploration interest you most?'),
    ('770e8400-e29b-41d4-a716-446655440008', '550e8400-e29b-41d4-a716-446655440008', 'Underground Laboratory', 'Secret research facility beneath the city for conducting advanced experiments.', 'You are in a high-tech underground laboratory filled with mysterious equipment, glowing screens, and the hum of advanced machinery.', 'Welcome to Laboratory Complex Omega! You''ve gained access to our most advanced research facility. The equipment around us represents the cutting edge of scientific innovation. What experiments or research topics would you like to explore in our secure environment?');

-- Insert test character_scene associations
INSERT INTO character_scene (character_id, scene_id) VALUES
    -- Helpful Assistant works well in office and coffee shop environments
    ('660e8400-e29b-41d4-a716-446655440000', '770e8400-e29b-41d4-a716-446655440000'), -- Helpful Assistant + Office Environment
    ('660e8400-e29b-41d4-a716-446655440000', '770e8400-e29b-41d4-a716-446655440001'), -- Helpful Assistant + Cozy Coffee Shop
    ('660e8400-e29b-41d4-a716-446655440000', '770e8400-e29b-41d4-a716-446655440006'), -- Helpful Assistant + Beach Resort
    
    -- Code Mentor is perfect for office and virtual reality environments
    ('660e8400-e29b-41d4-a716-446655440001', '770e8400-e29b-41d4-a716-446655440000'), -- Code Mentor + Office Environment
    ('660e8400-e29b-41d4-a716-446655440001', '770e8400-e29b-41d4-a716-446655440003'), -- Code Mentor + Virtual Reality Space
    ('660e8400-e29b-41d4-a716-446655440001', '770e8400-e29b-41d4-a716-446655440008'), -- Code Mentor + Underground Lab
    
    -- Creative Writer thrives in coffee shop and virtual reality spaces
    ('660e8400-e29b-41d4-a716-446655440002', '770e8400-e29b-41d4-a716-446655440001'), -- Creative Writer + Cozy Coffee Shop
    ('660e8400-e29b-41d4-a716-446655440002', '770e8400-e29b-41d4-a716-446655440003'), -- Creative Writer + Virtual Reality Space
    ('660e8400-e29b-41d4-a716-446655440002', '770e8400-e29b-41d4-a716-446655440005'), -- Creative Writer + Epic Fantasy
    
    -- Math Tutor is ideal for library and office environments
    ('660e8400-e29b-41d4-a716-446655440003', '770e8400-e29b-41d4-a716-446655440002'), -- Math Tutor + Library Study Room
    ('660e8400-e29b-41d4-a716-446655440003', '770e8400-e29b-41d4-a716-446655440000'), -- Math Tutor + Office Environment
    
    -- Dr. Sophisticated works in multiple environments
    ('660e8400-e29b-41d4-a716-446655440004', '770e8400-e29b-41d4-a716-446655440002'), -- Dr. Sophisticated + Library
    ('660e8400-e29b-41d4-a716-446655440004', '770e8400-e29b-41d4-a716-446655440007'), -- Dr. Sophisticated + Space Station
    ('660e8400-e29b-41d4-a716-446655440004', '770e8400-e29b-41d4-a716-446655440008'), -- Dr. Sophisticated + Underground Lab
    
    -- Simple Bot in minimal environments
    ('660e8400-e29b-41d4-a716-446655440005', '770e8400-e29b-41d4-a716-446655440004'), -- Simple Bot + Minimalist Scene
    
    -- Gaming Companion in virtual and fantasy environments
    ('660e8400-e29b-41d4-a716-446655440006', '770e8400-e29b-41d4-a716-446655440003'), -- Gaming Companion + Virtual Reality
    ('660e8400-e29b-41d4-a716-446655440006', '770e8400-e29b-41d4-a716-446655440005'), -- Gaming Companion + Epic Fantasy
    ('660e8400-e29b-41d4-a716-446655440006', '770e8400-e29b-41d4-a716-446655440007'), -- Gaming Companion + Space Station
    
    -- Meditation Guide in peaceful environments
    ('660e8400-e29b-41d4-a716-446655440007', '770e8400-e29b-41d4-a716-446655440006'), -- Meditation Guide + Beach Resort
    ('660e8400-e29b-41d4-a716-446655440007', '770e8400-e29b-41d4-a716-446655440004'), -- Meditation Guide + Minimalist Scene
    
    -- Travel Advisor in diverse locations
    ('660e8400-e29b-41d4-a716-446655440008', '770e8400-e29b-41d4-a716-446655440006'), -- Travel Advisor + Beach Resort
    ('660e8400-e29b-41d4-a716-446655440008', '770e8400-e29b-41d4-a716-446655440007'), -- Travel Advisor + Space Station
    ('660e8400-e29b-41d4-a716-446655440008', '770e8400-e29b-41d4-a716-446655440001'); -- Travel Advisor + Coffee Shop

-- Insert test chats
INSERT INTO chats (id, name, user_id, scene_id, created_at) VALUES
    ('550e8400-e29b-41d4-a716-446655440001', 'E2E Test Chat', '550e8400-e29b-41d4-a716-446655440000', '550e8400-e29b-41d4-a716-446655440001', NOW()),
    ('880e8400-e29b-41d4-a716-446655440000', 'Project Help Chat', '550e8400-e29b-41d4-a716-446655440000', '770e8400-e29b-41d4-a716-446655440000', NOW() - INTERVAL '2 days'),
    ('880e8400-e29b-41d4-a716-446655440001', 'Python Recursion Chat', '550e8400-e29b-41d4-a716-446655440001', '770e8400-e29b-41d4-a716-446655440001', NOW() - INTERVAL '1 day'),
    ('880e8400-e29b-41d4-a716-446655440002', 'Space Story Writing', '550e8400-e29b-41d4-a716-446655440002', '770e8400-e29b-41d4-a716-446655440002', NOW() - INTERVAL '12 hours'),
    ('880e8400-e29b-41d4-a716-446655440003', 'Calculus Help', '550e8400-e29b-41d4-a716-446655440003', '770e8400-e29b-41d4-a716-446655440002', NOW() - INTERVAL '6 hours'),
    ('880e8400-e29b-41d4-a716-446655440004', 'Fantasy ML Discussion', '550e8400-e29b-41d4-a716-446655440004', '770e8400-e29b-41d4-a716-446655440005', NOW() - INTERVAL '3 hours'),
    ('880e8400-e29b-41d4-a716-446655440005', 'Simple Chat', '550e8400-e29b-41d4-a716-446655440005', '770e8400-e29b-41d4-a716-446655440004', NOW() - INTERVAL '1 hour'),
    ('880e8400-e29b-41d4-a716-446655440006', 'RPG Strategy Chat', '550e8400-e29b-41d4-a716-446655440006', '770e8400-e29b-41d4-a716-446655440003', NOW() - INTERVAL '30 minutes'),
    ('880e8400-e29b-41d4-a716-446655440007', 'Stress Relief Session', '550e8400-e29b-41d4-a716-446655440007', '770e8400-e29b-41d4-a716-446655440006', NOW() - INTERVAL '15 minutes'),
    ('880e8400-e29b-41d4-a716-446655440008', 'Space Travel Planning', '550e8400-e29b-41d4-a716-446655440008', '770e8400-e29b-41d4-a716-446655440007', NOW() - INTERVAL '5 minutes'),
    ('880e8400-e29b-41d4-a716-446655440009', 'Mars Mission Chat', '550e8400-e29b-41d4-a716-446655440000', '770e8400-e29b-41d4-a716-446655440007', NOW() - INTERVAL '7 days'),
    ('880e8400-e29b-41d4-a716-446655440010', 'Quantum Computing Analysis', '550e8400-e29b-41d4-a716-446655440001', '770e8400-e29b-41d4-a716-446655440008', NOW() - INTERVAL '10 days');

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
    ('990e8400-e29b-41d4-a716-446655440008', '880e8400-e29b-41d4-a716-446655440003', 'model', 'I would be happy to help you with calculus derivatives! What specific topic would you like to focus on?', 12, NOW() - INTERVAL '6 hours' + INTERVAL '20 seconds'),
    
    -- Chat 5 messages (Dr. Sophisticated)
    ('990e8400-e29b-41d4-a716-446655440009', '880e8400-e29b-41d4-a716-446655440004', 'model', 'Welcome to the Epic Fantasy Adventure Scene. Your conversation will be enhanced by magical elements and rich storytelling.', 0, NOW() - INTERVAL '3 hours'),
    ('990e8400-e29b-41d4-a716-446655440010', '880e8400-e29b-41d4-a716-446655440004', 'user', 'Tell me about advanced machine learning techniques.', 0, NOW() - INTERVAL '3 hours' + INTERVAL '1 minute'),
    ('990e8400-e29b-41d4-a716-446655440011', '880e8400-e29b-41d4-a716-446655440004', 'model', 'Greetings! I shall illuminate the magnificent realm of advanced machine learning for you. In this magical domain of artificial intelligence, we encounter sophisticated techniques such as deep neural networks, transformer architectures, and reinforcement learning algorithms. These powerful methodologies represent the cutting edge of computational intelligence, capable of solving complex problems that were once thought impossible. Allow me to elaborate on each of these fascinating approaches...', 50, NOW() - INTERVAL '3 hours' + INTERVAL '2 minutes'),
    
    -- Chat 6 messages (Simple Bot)
    ('990e8400-e29b-41d4-a716-446655440012', '880e8400-e29b-41d4-a716-446655440005', 'user', 'Hi', 0, NOW() - INTERVAL '1 hour'),
    ('990e8400-e29b-41d4-a716-446655440013', '880e8400-e29b-41d4-a716-446655440005', 'model', 'Hi.', 1, NOW() - INTERVAL '1 hour' + INTERVAL '5 seconds'),
    
    -- Chat 7 messages (Gaming Companion)
    ('990e8400-e29b-41d4-a716-446655440014', '880e8400-e29b-41d4-a716-446655440006', 'user', 'What are the best strategies for playing RPGs?', 0, NOW() - INTERVAL '30 minutes'),
    ('990e8400-e29b-41d4-a716-446655440015', '880e8400-e29b-41d4-a716-446655440006', 'model', 'Great question! RPG strategies depend on the game type, but here are some universal tips...', 25, NOW() - INTERVAL '30 minutes' + INTERVAL '30 seconds'),
    
    -- Chat 8 messages (Meditation Guide)
    ('990e8400-e29b-41d4-a716-446655440016', '880e8400-e29b-41d4-a716-446655440007', 'user', 'I am feeling stressed. Can you help me relax?', 0, NOW() - INTERVAL '15 minutes'),
    ('990e8400-e29b-41d4-a716-446655440017', '880e8400-e29b-41d4-a716-446655440007', 'model', 'Of course. Let us begin with some deep breathing exercises. Find a comfortable position...', 18, NOW() - INTERVAL '15 minutes' + INTERVAL '45 seconds'),
    
    -- Chat 9 messages (Travel Advisor)
    ('990e8400-e29b-41d4-a716-446655440018', '880e8400-e29b-41d4-a716-446655440008', 'user', 'What destinations would you recommend for a space travel enthusiast?', 0, NOW() - INTERVAL '5 minutes'),
    ('990e8400-e29b-41d4-a716-446655440019', '880e8400-e29b-41d4-a716-446655440008', 'model', 'For space enthusiasts, I highly recommend visiting Kennedy Space Center in Florida, NASA Johnson Space Center in Houston, and the Griffith Observatory in Los Angeles for stunning astronomical views.', 35, NOW() - INTERVAL '5 minutes' + INTERVAL '1 minute'),
    
    -- Chat 10 messages (Long conversation)
    ('990e8400-e29b-41d4-a716-446655440020', '880e8400-e29b-41d4-a716-446655440009', 'model', 'This is a system message to initialize the space station environment for enhanced conversation context.', 0, NOW() - INTERVAL '7 days'),
    ('990e8400-e29b-41d4-a716-446655440021', '880e8400-e29b-41d4-a716-446655440009', 'user', 'How do you plan a trip to Mars?', 0, NOW() - INTERVAL '7 days' + INTERVAL '2 minutes'),
    ('990e8400-e29b-41d4-a716-446655440022', '880e8400-e29b-41d4-a716-446655440009', 'model', 'Planning a trip to Mars involves numerous complex considerations including launch windows, spacecraft design, life support systems, radiation protection, and mission duration. Current estimates suggest a journey would take 6-9 months each way.', 100, NOW() - INTERVAL '7 days' + INTERVAL '3 minutes'),
    ('990e8400-e29b-41d4-a716-446655440023', '880e8400-e29b-41d4-a716-446655440009', 'user', 'What about the psychological challenges?', 0, NOW() - INTERVAL '7 days' + INTERVAL '5 minutes'),
    ('990e8400-e29b-41d4-a716-446655440024', '880e8400-e29b-41d4-a716-446655440009', 'model', 'Excellent question! The psychological challenges are immense - isolation, confinement, communication delays with Earth, and the stress of knowing you cannot return quickly. Astronauts would need extensive mental health support.', 75, NOW() - INTERVAL '7 days' + INTERVAL '6 minutes'),
    
    -- Chat 11 messages (High cost conversation)
    ('990e8400-e29b-41d4-a716-446655440025', '880e8400-e29b-41d4-a716-446655440010', 'user', 'Write me a detailed analysis of quantum computing.', 0, NOW() - INTERVAL '10 days'),
    ('990e8400-e29b-41d4-a716-446655440026', '880e8400-e29b-41d4-a716-446655440010', 'model', 'Quantum computing represents a revolutionary paradigm in computational science, leveraging the principles of quantum mechanics to process information in fundamentally different ways than classical computers. This technology promises exponential speedups for certain types of problems...', 150, NOW() - INTERVAL '10 days' + INTERVAL '2 minutes');

-- Insert test media assets
INSERT INTO media_assets (id, file_url, entity_type, entity_id) VALUES
    ('aa0e8400-e29b-41d4-a716-446655440000', 'https://example.com/avatar1.png', 'character', '660e8400-e29b-41d4-a716-446655440000'),
    ('aa0e8400-e29b-41d4-a716-446655440001', 'https://example.com/avatar2.png', 'character', '660e8400-e29b-41d4-a716-446655440001'),
    ('aa0e8400-e29b-41d4-a716-446655440002', 'https://example.com/scene_bg1.jpg', 'scene', '770e8400-e29b-41d4-a716-446655440000'),
    ('aa0e8400-e29b-41d4-a716-446655440003', 'https://example.com/scene_bg2.jpg', 'scene', '770e8400-e29b-41d4-a716-446655440001'),
    ('aa0e8400-e29b-41d4-a716-446655440004', 'https://example.com/user_profile1.jpg', 'user', '550e8400-e29b-41d4-a716-446655440000'),
    ('aa0e8400-e29b-41d4-a716-446655440005', 'https://example.com/user_profile2.jpg', 'user', '550e8400-e29b-41d4-a716-446655440001'),
    ('aa0e8400-e29b-41d4-a716-446655440006', 'https://cdn.amazonaws.com/storage/characters/sophisticated-character-avatar-high-resolution.png', 'character', '660e8400-e29b-41d4-a716-446655440004'),
    ('aa0e8400-e29b-41d4-a716-446655440007', 'https://example.com/simple.gif', 'character', '660e8400-e29b-41d4-a716-446655440005'),
    ('aa0e8400-e29b-41d4-a716-446655440008', 'https://gaming-assets.s3.amazonaws.com/avatars/gaming_companion_animated.webp', 'character', '660e8400-e29b-41d4-a716-446655440006'),
    ('aa0e8400-e29b-41d4-a716-446655440009', 'https://meditation-images.cloudfront.net/peaceful-guide-portrait.svg', 'character', '660e8400-e29b-41d4-a716-446655440007'),
    ('aa0e8400-e29b-41d4-a716-446655440010', 'https://travel-media.example.org/advisor-profile-hd.jpeg', 'character', '660e8400-e29b-41d4-a716-446655440008'),
    ('aa0e8400-e29b-41d4-a716-446655440011', 'https://scene-backgrounds.cdn.example.com/fantasy-realm-ultra-wide-4k-background.tiff', 'scene', '770e8400-e29b-41d4-a716-446655440005'),
    ('aa0e8400-e29b-41d4-a716-446655440012', 'https://example.com/beach-paradise-360.jpg', 'scene', '770e8400-e29b-41d4-a716-446655440006'),
    ('aa0e8400-e29b-41d4-a716-446655440013', 'https://space-assets.nasa.gov/station-alpha-interior-panoramic.bmp', 'scene', '770e8400-e29b-41d4-a716-446655440007'),
    ('aa0e8400-e29b-41d4-a716-446655440014', 'https://underground-lab.tech-assets.com/laboratory-environment-dark.png', 'scene', '770e8400-e29b-41d4-a716-446655440008'),
    ('aa0e8400-e29b-41d4-a716-446655440015', 'https://user-profiles.example.com/premium-user-badge.ico', 'user', '550e8400-e29b-41d4-a716-446655440004'),
    ('aa0e8400-e29b-41d4-a716-446655440016', 'https://example.com/default-avatar.svg', 'user', '550e8400-e29b-41d4-a716-446655440005'),
    ('aa0e8400-e29b-41d4-a716-446655440017', 'https://profile-images.example.net/new-user-welcome-banner.webp', 'user', '550e8400-e29b-41d4-a716-446655440006'),
    ('aa0e8400-e29b-41d4-a716-446655440018', 'https://very-long-domain-name-for-testing-purposes.example.organization/extremely/long/path/structure/for/testing/url/length/limits/user-profile-image-with-very-descriptive-filename.jpg', 'user', '550e8400-e29b-41d4-a716-446655440007'),
    ('aa0e8400-e29b-41d4-a716-446655440019', 'https://inactive-user-assets.example.com/placeholder.png', 'user', '550e8400-e29b-41d4-a716-446655440008'),
    ('aa0e8400-e29b-41d4-a716-446655440020', 'https://minimal.example.com/bg.jpg', 'scene', '770e8400-e29b-41d4-a716-446655440004');

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
SELECT 'chats', COUNT(*) FROM chats
UNION ALL
SELECT 'messages', COUNT(*) FROM messages
UNION ALL
SELECT 'media_assets', COUNT(*) FROM media_assets;