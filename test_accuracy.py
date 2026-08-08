"""Unit test for accuracy fixes: spec code rejection, proper classification, deduplication."""
from src.utils.tag_classifier import classify_paddle_results
from src.agents.compiler import CompilerAgent

spec_items = [
    {'text': 'GC11S',  'confidence': 0.95},
    {'text': 'AS20S',  'confidence': 0.95},
    {'text': 'FC11S',  'confidence': 0.95},
    {'text': 'AC21',   'confidence': 0.95},
    {'text': 'GC115',  'confidence': 0.95},
    {'text': 'PV-26',  'confidence': 0.95},
    {'text': 'VA-26',  'confidence': 0.95},
]
real_items = [
    {'text': '26-PIT-9077',  'confidence': 0.95},
    {'text': 'PIT-9062',     'confidence': 0.95},
    {'text': '26-PDI-9054',  'confidence': 0.95},
    {'text': '26-TIT-9057',  'confidence': 0.95},
    {'text': 'PDIT-9054',    'confidence': 0.95},
    {'text': '26CB9131',     'confidence': 0.95},
    {'text': '26-GB-9178',   'confidence': 0.95},
    {'text': 'BV-101',       'confidence': 0.95},
    {'text': 'NV-201',       'confidence': 0.95},
    {'text': '26-KA-901',    'confidence': 0.95},
    {'text': 'KA-901',       'confidence': 0.95},
]

results = classify_paddle_results(spec_items + real_items, 'PID')
by_tag = {r['tag'].upper(): r for r in results}

pass_count = 0
fail_count = 0

def check(label, tag, expected_cls):
    global pass_count, fail_count
    r = by_tag.get(tag.upper())
    cls = r['classification'] if r else 'NOT_FOUND'
    if expected_cls == 'NOTE_OR_LINE':
        ok = cls in ('NOTE', 'LINE_TAG')
    else:
        ok = cls == expected_cls
    status = 'OK  ' if ok else 'FAIL'
    if ok:
        pass_count += 1
    else:
        fail_count += 1
    print(f'  [{status}] {label:35s} got: {cls}')

print('=== SPEC CODE REJECTION (must be NOTE) ===')
for s in ['GC11S', 'AS20S', 'FC11S', 'AC21', 'GC115', 'PV-26', 'VA-26']:
    check(s + ' must NOT be INSTRUMENT/EQUIPMENT', s, 'NOTE_OR_LINE')

print()
print('=== INSTRUMENT CLASSIFICATION ===')
for s in ['26-PIT-9077', 'PIT-9062', '26-PDI-9054', '26-TIT-9057', 'PDIT-9054']:
    check(s + ' must be INSTRUMENT_TAG', s, 'INSTRUMENT_TAG')

print()
print('=== VALVE CLASSIFICATION ===')
for s in ['26CB9131', '26-GB-9178', 'BV-101', 'NV-201']:
    check(s + ' must be VALVE_TAG', s, 'VALVE_TAG')

print()
print('=== EQUIPMENT DEDUP TEST ===')
ca = CompilerAgent()
etexts = [
    {'classification': 'EQUIPMENT_TAG', 'tag': '26-KA-901',    'value': '26-KA-901',    'attributes': {}},
    {'classification': 'EQUIPMENT_TAG', 'tag': 'KA-901',        'value': 'KA-901',       'attributes': {}},
    {'classification': 'EQUIPMENT_TAG', 'tag': '26-HA-911-C01', 'value': '26-HA-911-C01','attributes': {}},
    {'classification': 'EQUIPMENT_TAG', 'tag': 'HA-911',        'value': 'HA-911',       'attributes': {}},
]
equip = ca._compile_equipment(etexts, [])
eq_ok = len(equip) == 2
status = 'OK  ' if eq_ok else 'FAIL'
if eq_ok:
    pass_count += 1
else:
    fail_count += 1
print(f'  [{status}] 4 items -> {len(equip)} unique items (expected 2)')
for e in equip:
    print(f'         {e.tag:35s} type: {e.type}')

print()
print(f'=== RESULTS: {pass_count} passed, {fail_count} failed ===')
