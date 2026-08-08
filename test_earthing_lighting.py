"""Unit test for Earthing & Lighting / Electrical layout component extraction."""
from src.utils.tag_classifier import classify_paddle_results
from src.agents.compiler import CompilerAgent
from src.utils.line_tracer import trace_lines_and_connections

# Earthing test inputs
earthing_ocr = [
    {'text': 'EBM-01',           'confidence': 0.95},
    {'text': 'EB-101',           'confidence': 0.95},
    {'text': 'MAIN EARTH BAR',   'confidence': 0.95},
    {'text': 'EP-01',           'confidence': 0.95},
    {'text': 'EARTH PIT',        'confidence': 0.95},
    {'text': 'EARTH CHAMBER',    'confidence': 0.95},
    {'text': 'BC-01',            'confidence': 0.95},
    {'text': 'COPPER TAPE',      'confidence': 0.95},
    {'text': 'GS FLAT 50X6 MM',  'confidence': 0.95},
    {'text': '70 SQMM',          'confidence': 0.95},
]

# Lighting / Electrical test inputs
lighting_ocr = [
    {'text': 'L-01',             'confidence': 0.95},
    {'text': 'TL-101',          'confidence': 0.95},
    {'text': 'FL-01',           'confidence': 0.95},
    {'text': 'FLOODLIGHT-01',   'confidence': 0.95},
    {'text': 'WELLGLASS',       'confidence': 0.95},
    {'text': 'EMERGENCY LIGHT', 'confidence': 0.95},
    {'text': 'LIGHTING PANEL LP-01', 'confidence': 0.95},
    {'text': 'DB-01',           'confidence': 0.95},
    {'text': 'MDB-A',          'confidence': 0.95},
]

print("=== 1. CLASSIFIER EARTHING TEST ===")
e_results = classify_paddle_results(earthing_ocr, drawing_type="EARTHING_LAYOUT")
by_tag_e = {r['tag'].upper(): r for r in e_results}

earthing_expected = [
    ('EBM-01',          'EARTH_BAR_TAG'),
    ('EB-101',          'EARTH_BAR_TAG'),
    ('MAIN EARTH BAR',  'EARTH_BAR_TAG'),
    ('EP-01',          'EARTH_PIT_TAG'),
    ('EARTH PIT',       'EARTH_PIT_TAG'),
    ('EARTH CHAMBER',   'EARTH_PIT_TAG'),
    ('BC-01',           'BOND_CONDUCTOR_TAG'),
    ('COPPER TAPE',     'BOND_CONDUCTOR_TAG'),
    ('GS FLAT',         'BOND_CONDUCTOR_TAG'),
    ('70 SQMM',         'BOND_CONDUCTOR_TAG'),
]

e_pass = 0
for tag, exp_cls in earthing_expected:
    r = by_tag_e.get(tag.upper())
    got_cls = r['classification'] if r else 'NOT_FOUND'
    ok = got_cls == exp_cls
    if ok: e_pass += 1
    status = 'OK  ' if ok else 'FAIL'
    print(f'  [{status}] {tag:20s} -> {got_cls:20s} (expected {exp_cls})')

print(f'\nEarthing Classifier Results: {e_pass}/{len(earthing_expected)} passed')

print("\n=== 2. CLASSIFIER LIGHTING & ELECTRICAL TEST ===")
l_results = classify_paddle_results(lighting_ocr, drawing_type="ELECTRICAL_LAYOUT")
by_tag_l = {r['tag'].upper(): r for r in l_results}

lighting_expected = [
    ('L-01',                 'LUMINAIRE_TAG'),
    ('TL-101',              'LUMINAIRE_TAG'),
    ('FL-01',               'LUMINAIRE_TAG'),
    ('FLOODLIGHT-01',       'LUMINAIRE_TAG'),
    ('WELLGLASS',           'LUMINAIRE_TAG'),
    ('EMERGENCY LIGHT',     'LUMINAIRE_TAG'),
    ('LIGHTING PANEL LP',   'PANEL_TAG'),
    ('DB-01',               'PANEL_TAG'),
    ('MDB-A',              'PANEL_TAG'),
]

l_pass = 0
for tag, exp_cls in lighting_expected:
    r = by_tag_l.get(tag.upper())
    got_cls = r['classification'] if r else 'NOT_FOUND'
    ok = got_cls == exp_cls
    if ok: l_pass += 1
    status = 'OK  ' if ok else 'FAIL'
    print(f'  [{status}] {tag:25s} -> {got_cls:20s} (expected {exp_cls})')

print(f'\nLighting/Electrical Classifier Results: {l_pass}/{len(lighting_expected)} passed')

print("\n=== 3. COMPILER AGENT EARTHING & LIGHTING TEST ===")
ca = CompilerAgent()

# Compile earthing items
compiled_earth = ca._compile_earthing(e_results, [])
print(f'  Compiled {len(compiled_earth)} EarthingItem objects:')
for e in compiled_earth:
    print(f'    Tag: {e.tag:20s} | Type: {e.component_type:15s} | Material: {e.material} | Size: {e.size}')

# Compile luminaire items
compiled_lum = ca._compile_luminaires(l_results, [])
print(f'\n  Compiled {len(compiled_lum)} LuminaireItem objects:')
for lum in compiled_lum:
    print(f'    Tag: {lum.tag:25s} | Type: {lum.fitting_type:20s} | Wattage: {lum.wattage}')

# Compile panel items
compiled_pan = ca._compile_panels(l_results, [])
print(f'\n  Compiled {len(compiled_pan)} PanelItem objects:')
for pan in compiled_pan:
    print(f'    Tag: {pan.tag:25s} | Type: {pan.panel_type:20s} | Voltage: {pan.voltage}')

print("\n=== 4. LINE TRACER TOPOLOGICAL RELATIONS TEST ===")
all_entities = e_results + l_results + [{'classification': 'EQUIPMENT_TAG', 'tag': 'P-101', 'attributes': {}}]
tracer_res = trace_lines_and_connections(None, all_entities, [], drawing_type="EARTHING_LAYOUT")

relations = tracer_res['relations']
print(f'  Generated {len(relations)} topological relations:')
for rel in relations:
    print(f'    {rel["source_tag"]:25s} --[{rel["rel_type"]}]--> {rel["target_tag"]}')

total_tests = len(earthing_expected) + len(lighting_expected)
total_passed = e_pass + l_pass
print(f'\n=== FINAL SCORE: {total_passed}/{total_tests} tests passed ===')
