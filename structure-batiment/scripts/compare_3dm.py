#!/usr/bin/env python3
"""Compare layer structure and object metadata between two .3dm files."""
import json, os
from collections import defaultdict
import rhino3dm

BEFORE = '/Users/nicolaslecluse/Documents/GitHub/necs/structure-batiment/data/input/before.3dm'
AFTER  = '/Users/nicolaslecluse/Documents/GitHub/necs/structure-batiment/data/input/after.3dm'
OUTPUT_DIR = '/private/tmp/claude-501/-Users-nicolaslecluse-Documents-GitHub-necs-structure-batiment/b09d2d51-6bea-4e28-bc0f-f3133f5afc34/scratchpad'
OUTPUT_FILE = os.path.join(OUTPUT_DIR, 'layer_structure_comparison.json')

def color_to_dict(c):
    try:
        return {'R': c.R, 'G': c.G, 'B': c.B, 'A': c.A}
    except Exception:
        try:
            return {'R': c[0], 'G': c[1], 'B': c[2], 'A': c[3] if len(c)>3 else 255}
        except Exception:
            return str(c)

def brep_details(geom):
    info = {}
    for an, key in [('Faces','faces_count'),('Edges','edges_count'),('Vertices','vertices_count'),('Surfaces','surfaces_count'),('Trims','trims_count'),('Loops','loops_count')]:
        try:
            info[key] = len(getattr(geom, an))
        except Exception:
            info[key] = 'N/A'
    face_details = []
    try:
        for i in range(len(geom.Faces)):
            fd = {'face_index': i}
            try:
                fd['surface_index'] = geom.Faces[i].SurfaceIndex
            except Exception:
                pass
            face_details.append(fd)
    except Exception:
        pass
    if face_details: info['face_details'] = face_details
    return info

def extract_object_info(obj, lmap):
    geom, attr = obj.Geometry, obj.Attributes
    info = {
        'id': str(attr.Id) if attr else None,
        'name': attr.Name if attr else None,
        'layer_index': attr.LayerIndex if attr else None,
        'layer_name': lmap.get(attr.LayerIndex, 'UNKNOWN') if attr else 'UNKNOWN',
        'geometry_type': type(geom).__name__ if geom else 'None',
        'geometry_class': type(geom).__name__ if geom else None,
    }
    if attr:
        try:
            info['color'] = color_to_dict(attr.ObjectColor)
        except Exception:
            info['color'] = None
        try:
            info['color_source'] = int(attr.ColorSource)
        except Exception:
            info['color_source'] = None
        for aname in ['LinetypeIndex','MaterialIndex','Visible']:
            try:
                info[aname[0].lower()+aname[1:]] = getattr(attr, aname)
            except Exception:
                pass
        try:
            info['mode'] = int(attr.Mode)
        except Exception:
            pass
    if geom is not None:
        gtype = type(geom).__name__
        info['is_brep'] = 'Brep' in gtype
        if info['is_brep']:
            info['brep'] = brep_details(geom)
        info['is_extrusion'] = 'Extrusion' in gtype
        if info['is_extrusion']:
            try:
                info['extrusion_profile_count'] = geom.ProfileCount
            except Exception:
                pass
        info['is_mesh'] = 'Mesh' in gtype
        if info['is_mesh']:
            try:
                info['mesh_vertices'] = len(geom.Vertices)
            except Exception:
                pass
            try:
                info['mesh_faces'] = len(geom.Faces)
            except Exception:
                pass
        info['is_surface'] = 'Surface' in gtype
        try:
            bb = geom.GetBoundingBox()
            info['bounding_box'] = {'min': [bb.Min.X,bb.Min.Y,bb.Min.Z], 'max': [bb.Max.X,bb.Max.Y,bb.Max.Z]}
        except Exception:
            pass
    return info

def extract_layer_hierarchy(f3dm):
    layers_info, idx_name = [], {}
    for i, layer in enumerate(f3dm.Layers):
        idx_name[i] = layer.Name
        li = {'index': i, 'name': layer.Name, 'id': str(layer.Id), 'parent_id': str(layer.ParentLayerId),
              'color': color_to_dict(layer.Color), 'visible': layer.Visible, 'locked': layer.Locked}
        try:
            li['full_path'] = layer.FullPath
        except Exception:
            li['full_path'] = layer.Name
        layers_info.append(li)
    return layers_info, idx_name

def extract_file_metadata(f3dm):
    meta, s = {}, f3dm.Settings
    pairs = [('ModelUnitSystem','model_unit_system'),('ModelAbsoluteTolerance','model_absolute_tolerance'),
             ('ModelAngleToleranceRadians','model_angle_tolerance_radians'),('ModelAngleToleranceDegrees','model_angle_tolerance_degrees'),
             ('ModelRelativeTolerance','model_relative_tolerance'),('PageUnitSystem','page_unit_system'),('PageAbsoluteTolerance','page_absolute_tolerance')]
    for an, key in pairs:
        try:
            val = getattr(s, an)
            meta[key] = str(val) if 'Unit' in an else val
        except Exception:
            pass
    return meta

def analyze_file(filepath):
    f = rhino3dm.File3dm.Read(filepath)
    if f is None:
        raise RuntimeError('Could not open ' + filepath)
    layers, idx_name = extract_layer_hierarchy(f)
    metadata = extract_file_metadata(f)
    objects = []
    opl = defaultdict(int)
    gtc = defaultdict(int)
    ext_c = mesh_c = surf_c = brep_c = 0
    for obj in f.Objects:
        info = extract_object_info(obj, idx_name)
        objects.append(info)
        opl[info['layer_name']] += 1
        gtc[info['geometry_class'] or 'None'] += 1
        if info.get('is_extrusion'): ext_c += 1
        if info.get('is_mesh'): mesh_c += 1
        if info.get('is_surface'): surf_c += 1
        if info.get('is_brep'): brep_c += 1
    return {'filepath': filepath, 'layers': layers, 'layer_index_to_name': {str(k):v for k,v in idx_name.items()},
            'metadata': metadata, 'objects': objects, 'total_objects': len(objects),
            'object_count_per_layer': dict(opl), 'geometry_type_counts': dict(gtc),
            'extrusion_count': ext_c, 'mesh_count': mesh_c, 'surface_count': surf_c, 'brep_count': brep_c}

def compare(before, after):
    report = {}
    bln = {l['name'] for l in before['layers']}
    aln = {l['name'] for l in after['layers']}
    blm = {l['name']: l for l in before['layers']}
    alm = {l['name']: l for l in after['layers']}
    layer_diff = []
    for name in sorted(bln & aln):
        diffs = {}
        for key in ['id','parent_id','color','visible','locked','full_path']:
            bv = blm[name].get(key)
            av = alm[name].get(key)
            if bv != av: diffs[key] = {'before': bv, 'after': av}
        if diffs: layer_diff.append({'layer': name, 'changes': diffs})
    report['layers'] = {'before_count': len(before['layers']), 'after_count': len(after['layers']),
                        'added': sorted(aln-bln), 'removed': sorted(bln-aln), 'common': sorted(bln&aln), 'attribute_diffs': layer_diff}
    opl = {}
    for ln in sorted(bln | aln):
        bc = before['object_count_per_layer'].get(ln, 0)
        ac = after['object_count_per_layer'].get(ln, 0)
        opl[ln] = {'before': bc, 'after': ac, 'diff': ac - bc}
    report['object_count_per_layer'] = opl
    bids = {o['id'] for o in before['objects']}
    aids = {o['id'] for o in after['objects']}
    bom = {o['id']: o for o in before['objects']}
    aom = {o['id']: o for o in after['objects']}
    added_ids = sorted(aids - bids)
    removed_ids = sorted(bids - aids)
    common_ids = bids & aids
    report['objects_added_removed'] = {
        'total_before': before['total_objects'], 'total_after': after['total_objects'],
        'added_count': len(added_ids), 'removed_count': len(removed_ids), 'common_count': len(common_ids),
        'added': [{'id':i,'name':aom[i]['name'],'layer':aom[i]['layer_name'],'geometry_type':aom[i]['geometry_class']} for i in added_ids],
        'removed': [{'id':i,'name':bom[i]['name'],'layer':bom[i]['layer_name'],'geometry_type':bom[i]['geometry_class']} for i in removed_ids],
    }
    gtc = []
    for oid in sorted(common_ids):
        if bom[oid]['geometry_class'] != aom[oid]['geometry_class']:
            gtc.append({'id':oid,'name':bom[oid]['name'],'before_type':bom[oid]['geometry_class'],'after_type':aom[oid]['geometry_class']})
    report['geometry_type_changes'] = gtc
    report['geometry_type_counts'] = {'before': before['geometry_type_counts'], 'after': after['geometry_type_counts']}
    attr_diffs = []
    for oid in sorted(common_ids):
        changes = {}
        for k in ['name','layer_name','color','color_source','visible','mode','linetypeIndex','materialIndex']:
            bv = bom[oid].get(k)
            av = aom[oid].get(k)
            if bv != av: changes[k] = {'before': bv, 'after': av}
        if changes: attr_diffs.append({'id':oid,'name':bom[oid]['name'],'changes':changes})
    report['object_attribute_diffs'] = attr_diffs
    mk = set(list(before['metadata'].keys()) + list(after['metadata'].keys()))
    report['file_metadata'] = {}
    for k in sorted(mk):
        bv = before['metadata'].get(k)
        av = after['metadata'].get(k)
        report['file_metadata'][k] = {'before': bv, 'after': av, 'changed': bv != av}
    report['special_geometry_counts'] = {
        'extrusions': {'before': before['extrusion_count'], 'after': after['extrusion_count']},
        'meshes': {'before': before['mesh_count'], 'after': after['mesh_count']},
        'surfaces': {'before': before['surface_count'], 'after': after['surface_count']},
        'breps': {'before': before['brep_count'], 'after': after['brep_count']},
    }
    brep_cmp = []
    for oid in sorted(common_ids):
        if bom[oid].get('is_brep') or aom[oid].get('is_brep'):
            bb = bom[oid].get('brep', {})
            ab = aom[oid].get('brep', {})
            entry = {'id': oid, 'name': bom[oid]['name'], 'layer': bom[oid]['layer_name']}
            for fld in ['faces_count','edges_count','vertices_count','surfaces_count','trims_count','loops_count']:
                bv = bb.get(fld)
                av = ab.get(fld)
                entry[fld] = {'before': bv, 'after': av, 'same': bv == av}
            entry['vertices_same'] = bb.get('vertices_count') == ab.get('vertices_count')
            t_s = bb.get('trims_count') == ab.get('trims_count')
            f_s = bb.get('faces_count') == ab.get('faces_count')
            l_s = bb.get('loops_count') == ab.get('loops_count')
            entry['trim_face_topology_same'] = t_s and f_s and l_s
            brep_cmp.append(entry)
    report['brep_topology_comparison'] = brep_cmp
    return report

def print_summary(before, after, report):
    sep = '=' * 80
    print(sep)
    print('  3DM FILE COMPARISON REPORT')
    print(sep)
    lr = report['layers']
    print('\n1. LAYER HIERARCHY')
    print('  Layers in BEFORE:', lr['before_count'], ' |  Layers in AFTER:', lr['after_count'])
    print('  Added:', lr['added'] if lr['added'] else '(none)')
    print('  Removed:', lr['removed'] if lr['removed'] else '(none)')
    print('\n  BEFORE layers:')
    for l in before['layers']:
        pi = '  parent=' + l['parent_id'] if l['parent_id'] != '00000000-0000-0000-0000-000000000000' else ''
        print('    [' + str(l['index']) + '] ' + l['full_path'] + '  id=' + l['id'] + pi)
    print('\n  AFTER layers:')
    for l in after['layers']:
        pi = '  parent=' + l['parent_id'] if l['parent_id'] != '00000000-0000-0000-0000-000000000000' else ''
        print('    [' + str(l['index']) + '] ' + l['full_path'] + '  id=' + l['id'] + pi)
    if lr['attribute_diffs']:
        print('\n  Layer attribute changes:')
        for d in lr['attribute_diffs']:
            print('    ' + d['layer'] + ': ' + json.dumps(d['changes'], default=str))
    else:
        print('  No attribute changes on common layers.')
    print('\n2. OBJECT COUNT PER LAYER')
    print('  ' + 'Layer'.ljust(40) + 'Before'.rjust(7) + 'After'.rjust(7) + 'Diff'.rjust(7))
    for ln, v in report['object_count_per_layer'].items():
        ds = '+' + str(v['diff']) if v['diff'] > 0 else str(v['diff'])
        m = ' ***' if v['diff'] != 0 else ''
        print('  ' + ln.ljust(40) + str(v['before']).rjust(7) + str(v['after']).rjust(7) + ds.rjust(7) + m)
    ar = report['objects_added_removed']
    print('\n3. OBJECTS ADDED / REMOVED')
    print('  Total BEFORE:', ar['total_before'], ' AFTER:', ar['total_after'], ' Common:', ar['common_count'], ' Added:', ar['added_count'], ' Removed:', ar['removed_count'])
    for label, lst in [('Added', ar['added']), ('Removed', ar['removed'])]:
        if lst:
            print('  ' + label + ':')
            for o in lst[:20]:
                print('    id=' + o['id'] + '  name=' + repr(o['name']) + '  layer=' + o['layer'] + '  type=' + str(o['geometry_type']))
            if len(lst) > 20: print('    ... and ' + str(len(lst)-20) + ' more')
    print('\n4. GEOMETRY TYPES')
    print('  BEFORE:', json.dumps(before['geometry_type_counts']))
    print('  AFTER: ', json.dumps(after['geometry_type_counts']))
    if report['geometry_type_changes']:
        for c in report['geometry_type_changes']:
            print('  CHANGED: ' + c['id'] + ' ' + repr(c['name']) + ' ' + c['before_type'] + ' -> ' + c['after_type'])
    else:
        print('  No geometry type changes.')
    print('\n5. OBJECT ATTRIBUTE DIFFS')
    ad = report['object_attribute_diffs']
    if ad:
        print('  ' + str(len(ad)) + ' objects differ:')
        for d in ad[:30]:
            print('    ' + d['id'] + '  name=' + repr(d['name']))
            for k, v in d['changes'].items():
                print('      ' + k + ': ' + str(v['before']) + ' -> ' + str(v['after']))
    else:
        print('  No attribute diffs.')
    print('\n6. FILE METADATA')
    for k, v in report['file_metadata'].items():
        ch = '  ***' if v['changed'] else ''
        print('  ' + k + ': before=' + str(v['before']) + '  after=' + str(v['after']) + ch)
    print('\n7. SPECIAL GEOMETRY COUNTS')
    for gt, c in report['special_geometry_counts'].items():
        d = c['after'] - c['before']
        ds = '+' + str(d) if d > 0 else str(d)
        m = ' ***' if d != 0 else ''
        print('  ' + gt.ljust(12) + ' before=' + str(c['before']).rjust(5) + '  after=' + str(c['after']).rjust(5) + '  diff=' + ds + m)
    print('\n8-10. BREP TOPOLOGY')
    bc = report['brep_topology_comparison']
    if bc:
        changed = [b for b in bc if not b['vertices_same'] or not b['trim_face_topology_same']]
        unchanged = [b for b in bc if b['vertices_same'] and b['trim_face_topology_same']]
        print('  ' + str(len(bc)) + ' Breps compared: Unchanged=' + str(len(unchanged)) + ' Changed=' + str(len(changed)))
        if changed:
            for b in changed[:30]:
                print('  CHANGED: ' + b['id'] + '  name=' + repr(b['name']) + '  layer=' + b['layer'])
                for fld in ['faces_count','edges_count','vertices_count','trims_count','loops_count','surfaces_count']:
                    if not b[fld]['same']:
                        print('    ' + fld + ': ' + str(b[fld]['before']) + ' -> ' + str(b[fld]['after']))
                print('    vertices_same=' + str(b['vertices_same']) + '  trim_face_topology_same=' + str(b['trim_face_topology_same']))
        else:
            print('  All Breps identical.')
        if unchanged:
            print('  Sample unchanged (first 5):')
            for b in unchanged[:5]:
                print('    ' + b['id'] + '  name=' + repr(b['name']) + '  F=' + str(b['faces_count']['before']) + ' E=' + str(b['edges_count']['before']) + ' V=' + str(b['vertices_count']['before']))
    else:
        print('  No common Breps.')
    print('\n' + sep)
    print('  END OF REPORT')
    print(sep)

print('Reading BEFORE:', BEFORE)
before_data = analyze_file(BEFORE)
print('  ->', before_data['total_objects'], 'objects,', len(before_data['layers']), 'layers')
print('Reading AFTER: ', AFTER)
after_data = analyze_file(AFTER)
print('  ->', after_data['total_objects'], 'objects,', len(after_data['layers']), 'layers')
print('\nComparing...\n')
report = compare(before_data, after_data)
print_summary(before_data, after_data, report)
full_output = {'before_file': BEFORE, 'after_file': AFTER,
    'before_analysis': {k: before_data[k] for k in ['layers','metadata','total_objects','object_count_per_layer','geometry_type_counts','extrusion_count','mesh_count','surface_count','brep_count','objects']},
    'after_analysis': {k: after_data[k] for k in ['layers','metadata','total_objects','object_count_per_layer','geometry_type_counts','extrusion_count','mesh_count','surface_count','brep_count','objects']},
    'comparison': report}
os.makedirs(OUTPUT_DIR, exist_ok=True)
with open(OUTPUT_FILE, 'w', encoding='utf-8') as fout:
    json.dump(full_output, fout, indent=2, default=str)
print('\nFull results saved to:', OUTPUT_FILE)
