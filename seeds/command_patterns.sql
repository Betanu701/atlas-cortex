# Atlas Cortex — Seed Command Patterns
# These are the initial hardcoded patterns loaded on first run.
# The nightly evolution job will generate more patterns automatically.

INSERT INTO command_patterns (pattern, intent, entity_domain, entity_match_group, value_match_group, response_template, source, confidence) VALUES

-- Lights: on/off
('(?i)turn (on|off) (?:the )?(.+?)(?:\s+lights?)?$', 'toggle', 'light', 2, NULL, 'Done — {entity} turned {value}.', 'seed', 1.0),
('(?i)(?:switch|flip) (on|off) (?:the )?(.+?)(?:\s+lights?)?$', 'toggle', 'light', 2, NULL, 'Done — {entity} switched {value}.', 'seed', 0.9),
('(?i)lights? (on|off) (?:in )?(?:the )?(.+)$', 'toggle', 'light', 2, NULL, '{entity} lights {value}.', 'seed', 0.8),

-- Lights: brightness
('(?i)(?:set|dim|brighten) (?:the )?(.+?)(?:\s+lights?)? to (\d+)\s*%?$', 'set_brightness', 'light', 1, 2, '{entity} set to {value}%.', 'seed', 1.0),
('(?i)dim (?:the )?(.+?)(?:\s+lights?)? to (\d+)\s*%?$', 'set_brightness', 'light', 1, 2, '{entity} dimmed to {value}%.', 'seed', 0.9),
('(?i)(?:make|set) (?:the )?(.+?)(?:\s+lights?)? (brighter|dimmer)$', 'adjust_brightness', 'light', 1, 2, 'Adjusting {entity} {value}.', 'seed', 0.8),

-- Switches: on/off
('(?i)turn (on|off) (?:the )?(.+?)(?:\s+switch)?$', 'toggle', 'switch', 2, NULL, 'Done — {entity} turned {value}.', 'seed', 0.7),

-- Climate: temperature
('(?i)set (?:the )?(?:thermostat|temperature|temp)(?: in (?:the )?(.+?))? to (\d+)\s*(?:degrees?|°)?(?:\s*[fFcC])?$', 'set_temperature', 'climate', 1, 2, 'Thermostat set to {value}°.', 'seed', 1.0),
('(?i)(?:make|set) (?:it |the house |the room )?(warmer|cooler|hotter|colder)$', 'adjust_temperature', 'climate', NULL, 1, 'Adjusting temperature — making it {value}.', 'seed', 0.8),

-- Climate: mode
('(?i)(?:set|switch|change) (?:the )?(?:thermostat|hvac|ac|heat)(?: mode)? to (heat|cool|auto|off|fan.only)$', 'set_hvac_mode', 'climate', NULL, 1, 'HVAC mode set to {value}.', 'seed', 1.0),

-- Locks
('(?i)(lock|unlock) (?:the )?(.+?)(?:\s+(?:door|lock))?$', 'lock', 'lock', 2, 1, '{entity} {value}ed.', 'seed', 1.0),

-- Covers (garage doors, blinds, curtains)
('(?i)(open|close) (?:the )?(.+?)(?:\s+(?:door|garage|blind|curtain|shade|cover))?$', 'cover', 'cover', 2, 1, '{entity} {value}d.', 'seed', 1.0),

-- Fans
('(?i)turn (on|off) (?:the )?(.+?)(?:\s+fan)?$', 'toggle', 'fan', 2, NULL, '{entity} fan turned {value}.', 'seed', 0.7),
('(?i)set (?:the )?(.+?)(?:\s+fan)? (?:speed |to )?(\d+|low|medium|high)$', 'set_fan_speed', 'fan', 1, 2, '{entity} fan set to {value}.', 'seed', 0.9),

-- Sensors (read-only)
('(?i)(?:what(?:''s| is) the )?(?:current )?temperature (?:in |of |at )?(?:the )?(.+)$', 'get_state', 'sensor', 1, NULL, 'The temperature in {entity} is {state}.', 'seed', 1.0),
('(?i)(?:what(?:''s| is) the )?humidity (?:in |of |at )?(?:the )?(.+)$', 'get_state', 'sensor', 1, NULL, 'Humidity in {entity} is {state}%.', 'seed', 1.0),
('(?i)(?:is|are) (?:the )?(.+?) (open|closed|locked|unlocked|on|off)$', 'check_state', NULL, 1, 2, NULL, 'seed', 0.8),

-- Media players
('(?i)(pause|play|stop|next|previous|skip) (?:the )?(?:music|media|(.+))$', 'media_control', 'media_player', 2, 1, 'Media {value}.', 'seed', 0.9),
('(?i)(?:set|change) (?:the )?volume (?:of |on )?(?:the )?(.+?) to (\d+)\s*%?$', 'set_volume', 'media_player', 1, 2, '{entity} volume set to {value}%.', 'seed', 0.9),

-- Scenes and automations
('(?i)(?:activate|run|trigger|start) (?:the )?(.+?)(?:\s+(?:scene|automation|routine))?$', 'activate_scene', 'scene', 1, NULL, 'Activated {entity}.', 'seed', 0.6),
('(?i)(?:set|activate) (?:the )?(.+?) (?:scene|mode)$', 'activate_scene', 'scene', 1, NULL, '{entity} mode activated.', 'seed', 0.7),

-- Generic state query
('(?i)(?:what(?:''s| is) the )?(?:status|state) (?:of )?(?:the )?(.+)$', 'get_state', NULL, 1, NULL, '{entity} is currently {state}.', 'seed', 0.5);
