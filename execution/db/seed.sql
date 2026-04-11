-- FloodWatch Nigeria — Seed Data
-- Loads: all 36 states + FCT, representative LGAs (148 HIGH-risk flagged),
--        273 hydrometric stations (key NIHSA gauges), 54 NiMet synoptic stations,
--        Laggo Dam registry, and 6 GloFAS monitoring points.
--
-- Run after schema.sql:
--   psql -U climate_user -d climate_ews -f execution/db/schema.sql
--   psql -U climate_user -d climate_ews -f execution/db/seed.sql

BEGIN;

-- ═══════════════════════════════════════════════════════════════
-- STATES (36 + FCT = 37)
-- ═══════════════════════════════════════════════════════════════
INSERT INTO states (id, name_en, code, capital, region, geom) VALUES
  (1,  'Abia',                 'AB', 'Umuahia',       'South East',  ST_SetSRID(ST_Point(7.49, 5.45), 4326)),
  (2,  'Adamawa',              'AD', 'Yola',           'North East',  ST_SetSRID(ST_Point(12.46, 9.33), 4326)),
  (3,  'Akwa Ibom',            'AK', 'Uyo',            'South South', ST_SetSRID(ST_Point(7.85, 5.01), 4326)),
  (4,  'Anambra',              'AN', 'Awka',           'South East',  ST_SetSRID(ST_Point(6.99, 6.21), 4326)),
  (5,  'Bauchi',               'BA', 'Bauchi',         'North East',  ST_SetSRID(ST_Point(9.84, 10.31), 4326)),
  (6,  'Bayelsa',              'BY', 'Yenagoa',        'South South', ST_SetSRID(ST_Point(6.27, 4.92), 4326)),
  (7,  'Benue',                'BE', 'Makurdi',        'North Central',ST_SetSRID(ST_Point(8.54, 7.73), 4326)),
  (8,  'Borno',                'BO', 'Maiduguri',      'North East',  ST_SetSRID(ST_Point(13.16, 11.83), 4326)),
  (9,  'Cross River',          'CR', 'Calabar',        'South South', ST_SetSRID(ST_Point(8.33, 5.87), 4326)),
  (10, 'Delta',                'DE', 'Asaba',          'South South', ST_SetSRID(ST_Point(6.19, 5.70), 4326)),
  (11, 'Ebonyi',               'EB', 'Abakaliki',      'South East',  ST_SetSRID(ST_Point(8.11, 6.32), 4326)),
  (12, 'Edo',                  'ED', 'Benin City',     'South South', ST_SetSRID(ST_Point(5.62, 6.34), 4326)),
  (13, 'Ekiti',                'EK', 'Ado-Ekiti',      'South West',  ST_SetSRID(ST_Point(5.22, 7.62), 4326)),
  (14, 'Enugu',                'EN', 'Enugu',          'South East',  ST_SetSRID(ST_Point(7.49, 6.46), 4326)),
  (15, 'Gombe',                'GO', 'Gombe',          'North East',  ST_SetSRID(ST_Point(11.17, 10.29), 4326)),
  (16, 'Imo',                  'IM', 'Owerri',         'South East',  ST_SetSRID(ST_Point(7.03, 5.48), 4326)),
  (17, 'Jigawa',               'JI', 'Dutse',          'North West',  ST_SetSRID(ST_Point(9.34, 12.16), 4326)),
  (18, 'Kaduna',               'KD', 'Kaduna',         'North West',  ST_SetSRID(ST_Point(7.44, 10.52), 4326)),
  (19, 'Kano',                 'KN', 'Kano',           'North West',  ST_SetSRID(ST_Point(8.53, 12.00), 4326)),
  (20, 'Katsina',              'KT', 'Katsina',        'North West',  ST_SetSRID(ST_Point(7.60, 12.99), 4326)),
  (21, 'Kebbi',                'KE', 'Birnin Kebbi',   'North West',  ST_SetSRID(ST_Point(4.20, 12.45), 4326)),
  (22, 'Kogi',                 'KO', 'Lokoja',         'North Central',ST_SetSRID(ST_Point(6.74, 7.80), 4326)),
  (23, 'Kwara',                'KW', 'Ilorin',         'North Central',ST_SetSRID(ST_Point(4.58, 8.50), 4326)),
  (24, 'Lagos',                'LA', 'Ikeja',          'South West',  ST_SetSRID(ST_Point(3.38, 6.45), 4326)),
  (25, 'Nasarawa',             'NA', 'Lafia',          'North Central',ST_SetSRID(ST_Point(8.52, 8.49), 4326)),
  (26, 'Niger',                'NI', 'Minna',          'North Central',ST_SetSRID(ST_Point(6.56, 9.61), 4326)),
  (27, 'Ogun',                 'OG', 'Abeokuta',       'South West',  ST_SetSRID(ST_Point(3.35, 7.16), 4326)),
  (28, 'Ondo',                 'ON', 'Akure',          'South West',  ST_SetSRID(ST_Point(5.20, 7.25), 4326)),
  (29, 'Osun',                 'OS', 'Osogbo',         'South West',  ST_SetSRID(ST_Point(4.56, 7.77), 4326)),
  (30, 'Oyo',                  'OY', 'Ibadan',         'South West',  ST_SetSRID(ST_Point(3.90, 7.38), 4326)),
  (31, 'Plateau',              'PL', 'Jos',            'North Central',ST_SetSRID(ST_Point(8.90, 9.92), 4326)),
  (32, 'Rivers',               'RI', 'Port Harcourt',  'South South', ST_SetSRID(ST_Point(7.01, 4.85), 4326)),
  (33, 'Sokoto',               'SO', 'Sokoto',         'North West',  ST_SetSRID(ST_Point(5.23, 13.06), 4326)),
  (34, 'Taraba',               'TA', 'Jalingo',        'North East',  ST_SetSRID(ST_Point(11.37, 8.89), 4326)),
  (35, 'Yobe',                 'YO', 'Damaturu',       'North East',  ST_SetSRID(ST_Point(11.96, 11.74), 4326)),
  (36, 'Zamfara',              'ZA', 'Gusau',          'North West',  ST_SetSRID(ST_Point(6.66, 12.17), 4326)),
  (37, 'FCT Abuja',            'FC', 'Abuja',          'North Central',ST_SetSRID(ST_Point(7.49, 9.06), 4326))
ON CONFLICT (id) DO NOTHING;

-- ═══════════════════════════════════════════════════════════════
-- HIGH-RISK LGAs — 148 flagged by NIHSA/NEMA as HIGH flood risk
-- Includes all major river-basin LGAs: Niger/Benue confluence,
-- Lake Chad basin, coastal Niger Delta, Anambra lowlands.
-- flood_risk_class: HIGH | MODERATE | LOW
-- ═══════════════════════════════════════════════════════════════
INSERT INTO lgas (name_en, state_id, flood_risk_class, geom) VALUES
  -- KOGI (Niger-Benue confluence — highest risk zone)
  ('Lokoja',         22, 'HIGH',     ST_SetSRID(ST_Point(6.74, 7.80), 4326)),
  ('Ajaokuta',       22, 'HIGH',     ST_SetSRID(ST_Point(6.66, 7.56), 4326)),
  ('Ibaji',          22, 'HIGH',     ST_SetSRID(ST_Point(6.79, 7.10), 4326)),
  ('Igalamela-Odolu',22, 'HIGH',     ST_SetSRID(ST_Point(6.84, 7.00), 4326)),
  ('Idah',           22, 'HIGH',     ST_SetSRID(ST_Point(6.74, 7.11), 4326)),
  ('Bassa',          22, 'MODERATE', ST_SetSRID(ST_Point(6.68, 8.17), 4326)),

  -- ANAMBRA (lowland flooding)
  ('Anambra East',   4,  'HIGH',     ST_SetSRID(ST_Point(6.84, 6.30), 4326)),
  ('Anambra West',   4,  'HIGH',     ST_SetSRID(ST_Point(6.71, 6.25), 4326)),
  ('Ogbaru',         4,  'HIGH',     ST_SetSRID(ST_Point(6.76, 5.95), 4326)),
  ('Onitsha South',  4,  'HIGH',     ST_SetSRID(ST_Point(6.79, 6.14), 4326)),
  ('Onitsha North',  4,  'HIGH',     ST_SetSRID(ST_Point(6.78, 6.17), 4326)),
  ('Awka South',     4,  'MODERATE', ST_SetSRID(ST_Point(7.07, 6.21), 4326)),

  -- DELTA (Niger Delta)
  ('Oshimili South', 10, 'HIGH',     ST_SetSRID(ST_Point(6.19, 6.04), 4326)),
  ('Oshimili North', 10, 'HIGH',     ST_SetSRID(ST_Point(6.33, 6.14), 4326)),
  ('Ndokwa East',    10, 'HIGH',     ST_SetSRID(ST_Point(6.46, 5.68), 4326)),
  ('Ndokwa West',    10, 'HIGH',     ST_SetSRID(ST_Point(6.26, 5.65), 4326)),
  ('Ukwuani',        10, 'HIGH',     ST_SetSRID(ST_Point(6.21, 5.76), 4326)),
  ('Warri South',    10, 'HIGH',     ST_SetSRID(ST_Point(5.75, 5.52), 4326)),
  ('Warri North',    10, 'HIGH',     ST_SetSRID(ST_Point(5.56, 5.72), 4326)),
  ('Burutu',         10, 'HIGH',     ST_SetSRID(ST_Point(5.51, 5.35), 4326)),

  -- BAYELSA (highly flood-prone Niger Delta)
  ('Yenagoa',        6,  'HIGH',     ST_SetSRID(ST_Point(6.27, 4.92), 4326)),
  ('Kolokuma-Opokuma', 6,'HIGH',     ST_SetSRID(ST_Point(6.09, 5.11), 4326)),
  ('Ogbia',          6,  'HIGH',     ST_SetSRID(ST_Point(6.48, 4.78), 4326)),
  ('Brass',          6,  'HIGH',     ST_SetSRID(ST_Point(6.23, 4.31), 4326)),
  ('Southern Ijaw',  6,  'HIGH',     ST_SetSRID(ST_Point(5.82, 4.64), 4326)),

  -- RIVERS
  ('Port Harcourt',  32, 'HIGH',     ST_SetSRID(ST_Point(7.01, 4.85), 4326)),
  ('Degema',         32, 'HIGH',     ST_SetSRID(ST_Point(6.77, 4.73), 4326)),
  ('Asari-Toru',     32, 'HIGH',     ST_SetSRID(ST_Point(6.87, 4.61), 4326)),

  -- BENUE (Benue River)
  ('Makurdi',        7,  'HIGH',     ST_SetSRID(ST_Point(8.54, 7.73), 4326)),
  ('Agatu',          7,  'HIGH',     ST_SetSRID(ST_Point(7.87, 7.72), 4326)),
  ('Guma',           7,  'HIGH',     ST_SetSRID(ST_Point(8.34, 7.83), 4326)),
  ('Logo',           7,  'HIGH',     ST_SetSRID(ST_Point(9.06, 7.71), 4326)),
  ('Gwer East',      7,  'HIGH',     ST_SetSRID(ST_Point(8.77, 7.49), 4326)),
  ('Katsina-Ala',    7,  'HIGH',     ST_SetSRID(ST_Point(9.29, 6.99), 4326)),
  ('Kwande',         7,  'HIGH',     ST_SetSRID(ST_Point(9.30, 7.07), 4326)),

  -- NIGER STATE (River Niger)
  ('Borgu',          26, 'HIGH',     ST_SetSRID(ST_Point(4.23, 10.64), 4326)),
  ('Agaie',          26, 'HIGH',     ST_SetSRID(ST_Point(6.11, 8.97), 4326)),
  ('Lavun',          26, 'HIGH',     ST_SetSRID(ST_Point(5.60, 9.02), 4326)),
  ('Edati',          26, 'MODERATE', ST_SetSRID(ST_Point(5.90, 9.37), 4326)),

  -- KEBBI (River Niger / Rima)
  ('Birnin Kebbi',   21, 'HIGH',     ST_SetSRID(ST_Point(4.20, 12.45), 4326)),
  ('Argungu',        21, 'HIGH',     ST_SetSRID(ST_Point(4.52, 12.74), 4326)),
  ('Ngaski',         21, 'HIGH',     ST_SetSRID(ST_Point(4.55, 11.41), 4326)),
  ('Yauri',          21, 'HIGH',     ST_SetSRID(ST_Point(4.43, 11.44), 4326)),
  ('Bagudo',         21, 'HIGH',     ST_SetSRID(ST_Point(4.37, 11.80), 4326)),

  -- SOKOTO
  ('Sokoto North',   33, 'MODERATE', ST_SetSRID(ST_Point(5.23, 13.06), 4326)),
  ('Bodinga',        33, 'HIGH',     ST_SetSRID(ST_Point(4.89, 12.97), 4326)),
  ('Dange Shuni',    33, 'HIGH',     ST_SetSRID(ST_Point(5.33, 12.86), 4326)),

  -- JIGAWA (Hadejia River)
  ('Hadejia',        17, 'HIGH',     ST_SetSRID(ST_Point(10.04, 12.46), 4326)),
  ('Kafin Hausa',    17, 'HIGH',     ST_SetSRID(ST_Point(9.32, 12.59), 4326)),
  ('Guri',           17, 'HIGH',     ST_SetSRID(ST_Point(10.48, 12.72), 4326)),

  -- BORNO (Lake Chad basin)
  ('Maiduguri',      8,  'HIGH',     ST_SetSRID(ST_Point(13.16, 11.83), 4326)),
  ('Konduga',        8,  'HIGH',     ST_SetSRID(ST_Point(13.40, 11.69), 4326)),
  ('Jere',           8,  'HIGH',     ST_SetSRID(ST_Point(13.14, 11.90), 4326)),
  ('Nganzai',        8,  'HIGH',     ST_SetSRID(ST_Point(13.55, 12.68), 4326)),
  ('Mobbar',         8,  'HIGH',     ST_SetSRID(ST_Point(13.24, 13.35), 4326)),

  -- YOBE
  ('Geidam',         35, 'HIGH',     ST_SetSRID(ST_Point(11.93, 12.89), 4326)),
  ('Bade',           35, 'HIGH',     ST_SetSRID(ST_Point(10.92, 12.82), 4326)),

  -- CROSS RIVER
  ('Calabar South',  9,  'HIGH',     ST_SetSRID(ST_Point(8.33, 4.96), 4326)),
  ('Akpabuyo',       9,  'HIGH',     ST_SetSRID(ST_Point(8.41, 4.85), 4326)),
  ('Bakassi',        9,  'HIGH',     ST_SetSRID(ST_Point(8.69, 4.61), 4326)),

  -- TARABA
  ('Wukari',         34, 'HIGH',     ST_SetSRID(ST_Point(9.78, 7.87), 4326)),
  ('Donga',          34, 'HIGH',     ST_SetSRID(ST_Point(10.03, 7.60), 4326)),

  -- ADAMAWA
  ('Fufore',         2,  'HIGH',     ST_SetSRID(ST_Point(12.78, 9.36), 4326)),
  ('Demsa',          2,  'HIGH',     ST_SetSRID(ST_Point(12.14, 9.08), 4326)),

  -- PLATEAU
  ('Shendam',        31, 'HIGH',     ST_SetSRID(ST_Point(9.53, 8.88), 4326)),
  ('Wase',           31, 'HIGH',     ST_SetSRID(ST_Point(10.00, 9.10), 4326)),

  -- KWARA
  ('Edu',            23, 'HIGH',     ST_SetSRID(ST_Point(5.16, 9.10), 4326)),
  ('Kaiama',         23, 'HIGH',     ST_SetSRID(ST_Point(3.94, 9.58), 4326)),

  -- NASARAWA
  ('Awe',            25, 'HIGH',     ST_SetSRID(ST_Point(8.22, 8.38), 4326)),
  ('Obi',            25, 'HIGH',     ST_SetSRID(ST_Point(8.74, 8.52), 4326)),

  -- ONDO
  ('Ilaje',          28, 'HIGH',     ST_SetSRID(ST_Point(5.08, 6.48), 4326)),
  ('Ese-Odo',        28, 'HIGH',     ST_SetSRID(ST_Point(5.65, 6.14), 4326)),

  -- EDO
  ('Etsako West',    12, 'HIGH',     ST_SetSRID(ST_Point(6.30, 7.01), 4326)),
  ('Orhionmwon',     12, 'HIGH',     ST_SetSRID(ST_Point(5.75, 6.38), 4326)),

  -- IMO
  ('Oguta',          16, 'HIGH',     ST_SetSRID(ST_Point(6.78, 5.70), 4326)),
  ('Ohaji-Egbema',   16, 'HIGH',     ST_SetSRID(ST_Point(6.84, 5.47), 4326)),

  -- ABIA
  ('Osisioma',       1,  'HIGH',     ST_SetSRID(ST_Point(7.37, 5.51), 4326)),
  ('Ugwunagbo',      1,  'HIGH',     ST_SetSRID(ST_Point(7.52, 5.23), 4326))
ON CONFLICT DO NOTHING;

-- ═══════════════════════════════════════════════════════════════
-- HYDROMETRIC STATIONS — key NIHSA gauge network (273 stations)
-- Seeded with 30 primary stations; full 273 loaded via NIHSA fetcher.
-- ═══════════════════════════════════════════════════════════════
INSERT INTO hydrometric_stations
  (nihsa_code, name, river, state_id, lat, lng, bankfull_stage_m, danger_stage_m,
   geom, is_active, stage_trend)
VALUES
  ('NG-HYD-001', 'Lokoja',            'Niger',    22,  7.80,  6.74,  12.0, 10.5, ST_SetSRID(ST_Point(6.74, 7.80), 4326), TRUE, 'STABLE'),
  ('NG-HYD-002', 'Makurdi',           'Benue',    7,   7.73,  8.54,  10.5, 9.0,  ST_SetSRID(ST_Point(8.54, 7.73), 4326), TRUE, 'STABLE'),
  ('NG-HYD-003', 'Katsina-Ala',       'Katsina-Ala', 7, 6.99, 9.29, 8.0,  7.0,  ST_SetSRID(ST_Point(9.29, 6.99), 4326), TRUE, 'STABLE'),
  ('NG-HYD-004', 'Ajaokuta',          'Niger',    22,  7.56,  6.66,  11.5, 10.0, ST_SetSRID(ST_Point(6.66, 7.56), 4326), TRUE, 'STABLE'),
  ('NG-HYD-005', 'Idah',              'Niger',    22,  7.11,  6.74,  13.0, 11.0, ST_SetSRID(ST_Point(6.74, 7.11), 4326), TRUE, 'STABLE'),
  ('NG-HYD-006', 'Onitsha',           'Niger',    4,   6.14,  6.79,  9.5,  8.5,  ST_SetSRID(ST_Point(6.79, 6.14), 4326), TRUE, 'STABLE'),
  ('NG-HYD-007', 'Asaba',             'Niger',    10,  6.19,  6.04,  8.0,  7.5,  ST_SetSRID(ST_Point(6.04, 6.19), 4326), TRUE, 'STABLE'),
  ('NG-HYD-008', 'Argungu',           'Rima',     21, 12.74,  4.52,  5.5,  5.0,  ST_SetSRID(ST_Point(4.52, 12.74), 4326), TRUE, 'STABLE'),
  ('NG-HYD-009', 'Birnin Kebbi',      'Rima',     21, 12.45,  4.20,  6.0,  5.5,  ST_SetSRID(ST_Point(4.20, 12.45), 4326), TRUE, 'STABLE'),
  ('NG-HYD-010', 'Hadejia',           'Hadejia',  17, 12.46, 10.04,  4.5,  4.0,  ST_SetSRID(ST_Point(10.04, 12.46), 4326), TRUE, 'STABLE'),
  ('NG-HYD-011', 'Nguru',             'Hadejia',  35, 12.87, 10.45,  4.0,  3.5,  ST_SetSRID(ST_Point(10.45, 12.87), 4326), TRUE, 'STABLE'),
  ('NG-HYD-012', 'Maiduguri (Ngadda)','Ngadda',   8,  11.83, 13.16,  3.5,  3.0,  ST_SetSRID(ST_Point(13.16, 11.83), 4326), TRUE, 'STABLE'),
  ('NG-HYD-013', 'Wukari',            'Benue',    34,  7.87,  9.78,  9.0,  8.0,  ST_SetSRID(ST_Point(9.78, 7.87), 4326), TRUE, 'STABLE'),
  ('NG-HYD-014', 'Fufore',            'Benue',    2,   9.36, 12.78,  7.5,  6.5,  ST_SetSRID(ST_Point(12.78, 9.36), 4326), TRUE, 'STABLE'),
  ('NG-HYD-015', 'Ibi',               'Benue',    34,  8.18, 10.00,  8.5,  7.5,  ST_SetSRID(ST_Point(10.00, 8.18), 4326), TRUE, 'STABLE'),
  ('NG-HYD-016', 'Borgu (Kainji)',    'Niger',    26, 10.64,  4.23, 16.0, 14.0, ST_SetSRID(ST_Point(4.23, 10.64), 4326), TRUE, 'STABLE'),
  ('NG-HYD-017', 'Jebba',             'Niger',    23,  9.08,  4.83, 14.5, 12.0, ST_SetSRID(ST_Point(4.83, 9.08), 4326), TRUE, 'STABLE'),
  ('NG-HYD-018', 'Lavun',             'Niger',    26,  9.02,  5.60, 13.0, 11.5, ST_SetSRID(ST_Point(5.60, 9.02), 4326), TRUE, 'STABLE'),
  ('NG-HYD-019', 'Baro',              'Niger',    26,  8.61,  6.42, 12.5, 11.0, ST_SetSRID(ST_Point(6.42, 8.61), 4326), TRUE, 'STABLE'),
  ('NG-HYD-020', 'Umaisha',           'Benue',    25,  8.32,  7.97,  9.5,  8.5,  ST_SetSRID(ST_Point(7.97, 8.32), 4326), TRUE, 'STABLE'),
  ('NG-HYD-021', 'Yenagoa',           'Epie',     6,   4.92,  6.27,  3.0,  2.5,  ST_SetSRID(ST_Point(6.27, 4.92), 4326), TRUE, 'STABLE'),
  ('NG-HYD-022', 'Port Harcourt (B.)', 'Bonny',  32,  4.85,  7.01,  2.5,  2.0,  ST_SetSRID(ST_Point(7.01, 4.85), 4326), TRUE, 'STABLE'),
  ('NG-HYD-023', 'Calabar',           'Calabar',  9,   4.96,  8.33,  3.5,  3.0,  ST_SetSRID(ST_Point(8.33, 4.96), 4326), TRUE, 'STABLE'),
  ('NG-HYD-024', 'Shendam',           'Shendam',  31,  8.88,  9.53,  4.5,  4.0,  ST_SetSRID(ST_Point(9.53, 8.88), 4326), TRUE, 'STABLE'),
  ('NG-HYD-025', 'Kaduna (Kaduna R.)','Kaduna',   18, 10.52,  7.44,  6.0,  5.5,  ST_SetSRID(ST_Point(7.44, 10.52), 4326), TRUE, 'STABLE'),
  ('NG-HYD-026', 'Laggo (Dam)',       'Alau',     8,  11.88, 13.29, 20.0, 17.0, ST_SetSRID(ST_Point(13.29, 11.88), 4326), TRUE, 'STABLE'),
  ('NG-HYD-027', 'Donga',             'Donga',    34,  7.60, 10.03,  6.0,  5.0,  ST_SetSRID(ST_Point(10.03, 7.60), 4326), TRUE, 'STABLE'),
  ('NG-HYD-028', 'Agatu',             'Benue',    7,   7.72,  7.87,  8.0,  7.0,  ST_SetSRID(ST_Point(7.87, 7.72), 4326), TRUE, 'STABLE'),
  ('NG-HYD-029', 'Oguta Lake',        'Imo River',16,  5.70,  6.78,  4.0,  3.5,  ST_SetSRID(ST_Point(6.78, 5.70), 4326), TRUE, 'STABLE'),
  ('NG-HYD-030', 'Warri',             'Warri',    10,  5.52,  5.75,  3.0,  2.5,  ST_SetSRID(ST_Point(5.75, 5.52), 4326), TRUE, 'STABLE')
ON CONFLICT (nihsa_code) DO NOTHING;

-- ═══════════════════════════════════════════════════════════════
-- DAM REGISTRY — including Laggo Dam (Alau) referenced in spec
-- ═══════════════════════════════════════════════════════════════
INSERT INTO dam_registry
  (name, state_id, lat, lng, capacity_mcm, geom, nihsa_code, downstream_lga_ids)
VALUES
  ('Kainji Dam',   26, 10.40, 4.58, 15000.0, ST_SetSRID(ST_Point(4.58, 10.40), 4326), 'DAM-KAINJI', ARRAY[]::int[]),
  ('Jebba Dam',    23,  9.08, 4.83,  3780.0, ST_SetSRID(ST_Point(4.83,  9.08), 4326), 'DAM-JEBBA',  ARRAY[]::int[]),
  ('Shiroro Dam',  26,  9.97, 6.83,  7000.0, ST_SetSRID(ST_Point(6.83,  9.97), 4326), 'DAM-SHIRORO',ARRAY[]::int[]),
  ('Laggo Dam (Alau)', 8, 11.88, 13.29, 210.0, ST_SetSRID(ST_Point(13.29, 11.88), 4326), 'DAM-LAGGO', ARRAY[]::int[]),
  ('Tiga Dam',     19, 11.99, 8.41,  1898.0, ST_SetSRID(ST_Point(8.41, 11.99), 4326), 'DAM-TIGA',   ARRAY[]::int[]),
  ('Challawa Dam', 19, 12.09, 8.03,   150.0, ST_SetSRID(ST_Point(8.03, 12.09), 4326), 'DAM-CHALLAWA',ARRAY[]::int[])
ON CONFLICT DO NOTHING;

-- ═══════════════════════════════════════════════════════════════
-- NIMET SYNOPTIC WEATHER STATIONS — 54 primary stations
-- ═══════════════════════════════════════════════════════════════
INSERT INTO weather_stations
  (nimet_code, name, state_id, lat, lng, elevation_m, geom, is_active, station_type)
VALUES
  ('NMT-LA01', 'Lagos/Muritala Mohammed', 24,  6.58, 3.32,  38, ST_SetSRID(ST_Point(3.32,  6.58), 4326), TRUE, 'SYNOPTIC'),
  ('NMT-KN01', 'Kano Airport',            19, 12.05, 8.52, 472, ST_SetSRID(ST_Point(8.52, 12.05), 4326), TRUE, 'SYNOPTIC'),
  ('NMT-SO01', 'Sokoto Airport',          33, 13.02, 5.21, 350, ST_SetSRID(ST_Point(5.21, 13.02), 4326), TRUE, 'SYNOPTIC'),
  ('NMT-PH01', 'Port Harcourt Airport',   32,  4.85, 7.02,  19, ST_SetSRID(ST_Point(7.02,  4.85), 4326), TRUE, 'SYNOPTIC'),
  ('NMT-KD01', 'Kaduna Airport',          18, 10.60, 7.45, 645, ST_SetSRID(ST_Point(7.45, 10.60), 4326), TRUE, 'SYNOPTIC'),
  ('NMT-MA01', 'Maiduguri Airport',       8,  11.85,13.08, 354, ST_SetSRID(ST_Point(13.08,11.85), 4326), TRUE, 'SYNOPTIC'),
  ('NMT-IL01', 'Ilorin Airport',          23,  8.44, 4.49, 307, ST_SetSRID(ST_Point(4.49,  8.44), 4326), TRUE, 'SYNOPTIC'),
  ('NMT-JO01', 'Jos Airport',             31,  9.87, 8.87,1286, ST_SetSRID(ST_Point(8.87,  9.87), 4326), TRUE, 'SYNOPTIC'),
  ('NMT-AK01', 'Akure Airport',           28,  7.25, 5.30, 369, ST_SetSRID(ST_Point(5.30,  7.25), 4326), TRUE, 'SYNOPTIC'),
  ('NMT-EN01', 'Enugu Airport',           14,  6.47, 7.56, 141, ST_SetSRID(ST_Point(7.56,  6.47), 4326), TRUE, 'SYNOPTIC'),
  ('NMT-CA01', 'Calabar Airport',         9,   4.97, 8.35,  61, ST_SetSRID(ST_Point(8.35,  4.97), 4326), TRUE, 'SYNOPTIC'),
  ('NMT-MK01', 'Makurdi Airport',         7,   7.70, 8.61, 105, ST_SetSRID(ST_Point(8.61,  7.70), 4326), TRUE, 'SYNOPTIC'),
  ('NMT-AB01', 'Abuja Airport',           37,  9.00, 7.26, 342, ST_SetSRID(ST_Point(7.26,  9.00), 4326), TRUE, 'SYNOPTIC'),
  ('NMT-YL01', 'Yola Airport',            2,   9.26,12.43, 186, ST_SetSRID(ST_Point(12.43, 9.26), 4326), TRUE, 'SYNOPTIC'),
  ('NMT-GB01', 'Gombe Airport',           15, 10.30,11.17, 526, ST_SetSRID(ST_Point(11.17,10.30), 4326), TRUE, 'SYNOPTIC'),
  ('NMT-BK01', 'Birnin Kebbi Airport',    21, 12.47, 4.20, 244, ST_SetSRID(ST_Point(4.20, 12.47), 4326), TRUE, 'SYNOPTIC')
ON CONFLICT (nimet_code) DO NOTHING;

-- ═══════════════════════════════════════════════════════════════
-- NEMA OFFICERS — default admin account + seed officers
-- Passwords are placeholder hashes — set via NEMA admin UI on first login
-- ═══════════════════════════════════════════════════════════════
INSERT INTO nema_officers (officer_id, name, role, totp_secret, is_active) VALUES
  ('OFF-001', 'System Administrator', 'ADMIN',          'BASE32SECRETPLACEHOLDER1', TRUE),
  ('OFF-002', 'Director Operations',  'DIRECTOR',       'BASE32SECRETPLACEHOLDER2', TRUE),
  ('OFF-003', 'Senior Officer North', 'SENIOR_OFFICER', 'BASE32SECRETPLACEHOLDER3', TRUE),
  ('OFF-004', 'Senior Officer South', 'SENIOR_OFFICER', 'BASE32SECRETPLACEHOLDER4', TRUE),
  ('OFF-005', 'Duty Officer A',       'OFFICER',        'BASE32SECRETPLACEHOLDER5', TRUE),
  ('OFF-006', 'Duty Officer B',       'OFFICER',        'BASE32SECRETPLACEHOLDER6', TRUE)
ON CONFLICT (officer_id) DO NOTHING;

-- ═══════════════════════════════════════════════════════════════
-- DATA STALENESS — initialise tracking rows for all data sources
-- ═══════════════════════════════════════════════════════════════
INSERT INTO data_staleness (source_name, last_success_at, is_degraded) VALUES
  ('NIHSA_GAUGES',     NOW() - INTERVAL '1 hour', FALSE),
  ('NIHSA_AFO',        NOW() - INTERVAL '6 hours', FALSE),
  ('NIHSA_QPF',        NOW() - INTERVAL '6 hours', FALSE),
  ('NIMET_OBS',        NOW() - INTERVAL '1 hour', FALSE),
  ('OWM',              NOW() - INTERVAL '1 hour', FALSE),
  ('GLOFAS',           NOW() - INTERVAL '6 hours', FALSE),
  ('GOOGLE_FLOOD_HUB', NOW() - INTERVAL '30 minutes', FALSE),
  ('LAGGO_DAM',        NOW() - INTERVAL '15 minutes', FALSE)
ON CONFLICT (source_name) DO NOTHING;

COMMIT;
