-- Dev seed data: one apartment site, two gates, a few vehicles, one active visitor pass.
-- Fixed UUIDs so the backend and CV code can reference them while developing.

INSERT INTO sites (id, name, type)
VALUES ('11111111-1111-1111-1111-111111111111', 'Sunrise Apartments', 'apartment');

INSERT INTO gates (id, site_id, name, direction, camera_source) VALUES
  ('aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa', '11111111-1111-1111-1111-111111111111',
   'Main Entry', 'entry', 'data/videos/entry.mp4'),
  ('bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb', '11111111-1111-1111-1111-111111111111',
   'Main Exit',  'exit',  'data/videos/exit.mp4');

INSERT INTO vehicles (site_id, plate, owner_name, role, unit) VALUES
  ('11111111-1111-1111-1111-111111111111', 'TS09AB1234', 'Ravi Kumar',  'resident',    'A-101'),
  ('11111111-1111-1111-1111-111111111111', 'TS08CD5678', 'Anita Rao',   'staff',       'Security'),
  ('11111111-1111-1111-1111-111111111111', 'TS10EF9999', 'Unknown',     'blacklisted', NULL);

-- Valid from 1 hour ago to 6 hours ahead, so it works whenever you first start the DB
INSERT INTO visitor_passes (site_id, plate, visitor_name, host_name, host_unit, valid_from, valid_until)
VALUES ('11111111-1111-1111-1111-111111111111', 'TS07GH4321', 'Suresh', 'Ravi Kumar', 'A-101',
        now() - interval '1 hour', now() + interval '6 hours');
