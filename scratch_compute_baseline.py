import sys
import os
import re
import json
import openpyxl

sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, '.')

from src.utils.paddle_ocr import run_pdf_text_extraction
from src.utils.tag_classifier import classify_paddle_results, canonicalize_tag
from src.agents.compiler import CompilerAgent

# 1. Load Ground Truth for KA-901
wb = openpyxl.load_workbook(r'pid_stuff/PID_Extraction_RevB_Corrected_26-KA-901_902 (2).xlsx', data_only=True)

def get_ka901_tags(sheetname, tag_col=1):
    sheet = wb[sheetname]
    rows = list(sheet.iter_rows(values_only=True))
    tags = []
    in_ka901 = False
    for r in rows:
        if not r or not any(cell is not None for cell in r):
            continue
        c0 = str(r[0]).strip() if r[0] is not None else ''
        c1 = str(r[tag_col]).strip() if len(r) > tag_col and r[tag_col] is not None else ''
        if '26-KA-901' in c0:
            in_ka901 = True
            continue
        if '26-KA-902' in c0:
            in_ka901 = False
            continue
        if sheetname == 'Equipment List':
            if c1.startswith('26-KA-902') or c1 in ('26-KZ-902', '26-CX-9021', '26-CX-9222', '26-CK-921'):
                in_ka901 = False
            elif c1.startswith('26-KA-901') or c1 in ('26-KZ-901', '26-HA-911', '26-CX-9011', '26-CX-9122', '26-CK-911'):
                in_ka901 = True
        elif sheetname == 'Safety Relief Valve List':
            if '9066' in c1:
                in_ka901 = True
            elif '9027' in c1:
                in_ka901 = False

        if in_ka901 and c1 and not c1.startswith('#') and 'Tag' not in c1 and 'List' not in c1 and 'Line Number' not in c1:
            tags.append(c1)
    return tags

gt = {
    'EQUIPMENT': get_ka901_tags('Equipment List'),
    'PSV': get_ka901_tags('Safety Relief Valve List'),
    'INSTRUMENTS': get_ka901_tags('Instrument List'),
    'VALVES': get_ka901_tags('Manual Valve List'),
    'LINES': get_ka901_tags('Line List'),
}

# 2. Extract from Lift Gas compressor-PID.pdf
pdf_path = r'pid_stuff/Lift Gas compressor-PID.pdf'
ocr_items = run_pdf_text_extraction(pdf_path)
classified = classify_paddle_results(ocr_items, 'PID')

ca = CompilerAgent()
compiled_dict = {
    'EQUIPMENT': ca._compile_equipment(classified, []),
    'LINES': ca._compile_lines(classified, {}, []),
    'INSTRUMENTS': ca._compile_instruments(classified, [], [], []),
    'VALVES': ca._compile_valves(classified, [], [], []),
    'PSV': ca._compile_safety_relief_valves(classified, [])
}

def clean_tag(t):
    t = re.sub(r'^\d{2,3}-', '', t.upper().strip())
    for ch in [' ', '"', "'", '-']:
        t = t.replace(ch, '')
    return t

results = {}
total_tp, total_fp, total_fn, total_gt, total_comp = 0, 0, 0, 0, 0

for cat, gt_list in gt.items():
    comp_list = [item.tag for item in compiled_dict[cat]]
    gt_map = {clean_tag(t): t for t in gt_list}
    comp_map = [clean_tag(t) for t in comp_list]
    
    tp_gt = set()
    matched_comp = set()
    
    for c_idx, c_tag in enumerate(comp_map):
        # Exact clean match
        if c_tag in gt_map:
            tp_gt.add(c_tag)
            matched_comp.add(c_idx)
        else:
            # Partial match (e.g. sequence number or substring)
            for g_tag in gt_map:
                if (len(c_tag) >= 4 and c_tag in g_tag) or (len(g_tag) >= 4 and g_tag in c_tag):
                    tp_gt.add(g_tag)
                    matched_comp.add(c_idx)
                    break

    tp = len(tp_gt)
    fp = len(comp_list) - len(matched_comp)
    fn = len(gt_list) - tp
    
    rec = tp / len(gt_list) if gt_list else 0.0
    prec = len(matched_comp) / len(comp_list) if comp_list else 0.0
    f1 = 2 * prec * rec / (prec + rec) if (prec + rec) else 0.0
    
    results[cat] = {
        'gt_count': len(gt_list),
        'compiled_count': len(comp_list),
        'tp': tp,
        'fp': fp,
        'fn': fn,
        'recall': round(rec, 4),
        'precision': round(prec, 4),
        'f1': round(f1, 4),
        'matched_tags': [gt_map.get(k, k) for k in tp_gt],
        'missed_gt': [t for t in gt_list if clean_tag(t) not in tp_gt]
    }
    total_tp += tp
    total_comp += len(comp_list)
    total_gt += len(gt_list)
    total_fp += fp
    total_fn += fn

overall_rec = total_tp / total_gt if total_gt else 0.0
overall_prec = (total_comp - total_fp) / total_comp if total_comp else 0.0
overall_f1 = 2 * overall_prec * overall_rec / (overall_prec + overall_rec) if (overall_prec + overall_rec) else 0.0

baseline_metrics = {
    'raw_observation_count': len(ocr_items),
    'candidate_count': len(classified),
    'canonical_entity_count': total_comp,
    'overall_ground_truth_count': total_gt,
    'overall_tp': total_tp,
    'overall_fp': total_fp,
    'overall_fn': total_fn,
    'overall_recall': round(overall_rec, 4),
    'overall_precision': round(overall_prec, 4),
    'overall_f1': round(overall_f1, 4),
    'duplicate_rate': round(total_fp / total_comp if total_comp else 0.0, 4),
    'false_entity_rate': round(total_fp / total_comp if total_comp else 0.0, 4),
    'classification_error_rate': round((results['EQUIPMENT']['fp'] + results['INSTRUMENTS']['fp'] + results['VALVES']['fp']) / total_comp, 4),
    're_extraction_count': 0,
    'categories': results
}

print(json.dumps(baseline_metrics, indent=2))
with open('PRECISION_BASELINE.json', 'w', encoding='utf-8') as f:
    json.dump(baseline_metrics, f, indent=2)
print("Saved PRECISION_BASELINE.json successfully.")
