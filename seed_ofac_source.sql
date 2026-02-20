INSERT INTO sources (id, name, abbreviation, source_type, base_url, authority_level, is_active)
VALUES (
    gen_random_uuid(),
    'Office of Foreign Assets Control',
    'OFAC',
    'government',
    'https://www.treasury.gov/ofac',
    10,
    true
)
ON CONFLICT (abbreviation) DO NOTHING;
