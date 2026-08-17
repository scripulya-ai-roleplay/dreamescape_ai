-- 2026-08: per-asset ordering, captions and background/foreground layering.
--
-- Idempotent (safe to re-run; ADD COLUMN IF NOT EXISTS, constraint added only
-- when missing). init.sql already includes these columns for fresh volumes;
-- this file upgrades databases initialized before the change. All columns
-- are nullable or defaulted, so it is safe to run on a live database.

ALTER TABLE media_assets ADD COLUMN IF NOT EXISTS sort_order INTEGER NOT NULL DEFAULT 0;
ALTER TABLE media_assets ADD COLUMN IF NOT EXISTS caption VARCHAR(200);
ALTER TABLE media_assets ADD COLUMN IF NOT EXISTS layer VARCHAR(20) NOT NULL DEFAULT 'background';

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'check_media_layer_valid'
          AND conrelid = 'media_assets'::regclass
    ) THEN
        ALTER TABLE media_assets ADD CONSTRAINT check_media_layer_valid
            CHECK (layer IN ('background', 'foreground'));
    END IF;
END $$;

ALTER TABLE character_scene ADD COLUMN IF NOT EXISTS attached_at TIMESTAMPTZ NOT NULL DEFAULT NOW();
