-- Grammar DB migration for project ukizpcmhhwcryzcbixnn
-- Requires: GRAMMAR_SUPABASE_SERVICE_KEY (service role, not publishable key)
--
-- This migration:
--   1. Removes 6 overly-specific orphan nonterminals
--   2. Adds 7 symbols referenced in StructuralRules but missing from GrammarNodes
--
-- Run via Supabase SQL Editor or psql with service-role credentials.

BEGIN;

-- 1. Remove overly-specific orphan nonterminals (no rules reference them)
DELETE FROM "GrammarNodes"
WHERE short_form_name IN (
    'CLIMBING_LEG',
    'CLIMBING_LEG_PAIR',
    'FOLDED_WING_PAIR',
    'LOAD_BAY',
    'SHORT_LEG',
    'SHORT_LEG_PAIR'
);

-- 2. Add missing symbols that exist in StructuralRules RHS but not in GrammarNodes
-- These 7 symbols cause compile_structural_rules() to return invalid_nodes
INSERT INTO "GrammarNodes" (grammar_id, morphology_family, node, node_type, short_form_name, long_name, description, tags, active)
VALUES
    (1, 'general', 'body_joint', 'terminal', 'body_joint', 'Body Joint', 'Joint connecting body segments', '{}', true),
    (1, 'general', 'forearm', 'terminal', 'forearm', 'Forearm', 'Lower arm segment between elbow and wrist', '{}', true),
    (1, 'general', 'front_body_segment', 'terminal', 'front_body_segment', 'Front Body Segment', 'Anterior body segment', '{}', true),
    (1, 'general', 'mirror_left', 'terminal', 'mirror_left', 'Mirror Left', 'Left-side mirror symmetry operator', '{}', true),
    (1, 'general', 'mirror_right', 'terminal', 'mirror_right', 'Mirror Right', 'Right-side mirror symmetry operator', '{}', true),
    (1, 'general', 'rear_body_segment', 'terminal', 'rear_body_segment', 'Rear Body Segment', 'Posterior body segment', '{}', true),
    (1, 'general', 'upper_arm', 'terminal', 'upper_arm', 'Upper Arm', 'Upper arm segment between shoulder and elbow', '{}', true)
ON CONFLICT (short_form_name) DO NOTHING;

COMMIT;
