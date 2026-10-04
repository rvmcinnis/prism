"""Add furniture to a Prism floor-plan GLB. Usage: furnish.py in.glb out.glb"""
import sys, math, struct, json
import numpy as np
from shapely.geometry import Polygon, box as sbox
from shapely.ops import unary_union
from glb import load, acc

# ---------- part builders (local frame: origin at footprint center, front = +z) ----------
def B(x0, x1, y0, y1, z0, z1, mat):
    return (x0, x1, y0, y1, z0, z1, mat)

def legs(w, d, h, t=0.05, inset=0.03, mat='furniture-wood'):
    xs = (-w/2+inset, w/2-inset-t); zs = (-d/2+inset, d/2-inset-t)
    return [B(x, x+t, 0, h, z, z+t, mat) for x in xs for z in zs]

def bed(w, d):
    return [B(-w/2, w/2, 0.12, 0.32, -d/2+0.08, d/2, 'furniture-wood'),
            B(-w/2+0.02, w/2-0.02, 0.32, 0.56, -d/2+0.1, d/2-0.02, 'furniture-bed'),
            B(-w/2, w/2, 0, 1.1, -d/2, -d/2+0.08, 'furniture-wood'),
            *[B(cx-0.3, cx+0.3, 0.56, 0.68, -d/2+0.15, -d/2+0.55, 'furniture-upholstery')
              for cx in ((-w/4, w/4) if w > 1.2 else (0,))],
            *legs(w, d-0.08, 0.12)]

def casegood(w, d, h=None):  # nightstand, dresser, console, media unit
    h = h or (0.6 if w < 0.6 else 0.8)
    return [B(-w/2, w/2, 0.08, h, -d/2, d/2, 'furniture-wood'), *legs(w, d, 0.08, t=0.04, inset=0.02)]

def table(w, d, h=0.75, mat='furniture-wood'):
    return [B(-w/2, w/2, h-0.04, h, -d/2, d/2, mat), *legs(w, d, h-0.04, mat=mat)]

def chair(w=0.45, d=0.5, mat='furniture-wood', seat='furniture-upholstery'):
    return [*legs(w, d, 0.42, t=0.04, mat=mat), B(-w/2, w/2, 0.42, 0.47, -d/2, d/2, seat),
            B(-w/2, w/2, 0.47, 0.9, -d/2, -d/2+0.05, mat)]

def stool(s=0.4, h=0.75):
    return [*legs(s, s, h-0.05, t=0.04), B(-s/2, s/2, h-0.05, h, -s/2, s/2, 'furniture-wood'),
            B(-s/2+0.03, s/2-0.03, 0.25, 0.28, -s/2+0.03, s/2-0.03, 'furniture-wood')]

def sofa(w, d, mat='furniture-upholstery'):
    a = 0.18
    return [B(-w/2, w/2, 0.1, 0.45, -d/2, d/2, mat),
            B(-w/2, w/2, 0.45, 0.85, -d/2, -d/2+0.22, mat),
            B(-w/2, -w/2+a, 0.45, 0.62, -d/2, d/2, mat),
            B(w/2-a, w/2, 0.45, 0.62, -d/2, d/2, mat),
            *legs(w, d, 0.1, t=0.05)]

def shelving(w, d, h=1.8, n=5):
    t = 0.03
    parts = [B(-w/2, -w/2+t, 0, h, -d/2, d/2, 'furniture-wood'), B(w/2-t, w/2, 0, h, -d/2, d/2, 'furniture-wood'),
             B(-w/2, w/2, 0, h, -d/2, -d/2+t, 'furniture-wood')]
    for i in range(n):
        y = 0.05 + i*(h-0.08)/(n-1)
        parts.append(B(-w/2+t, w/2-t, y, y+t, -d/2+t, d/2, 'furniture-wood'))
    return parts

def wardrobe(w, d, h=2.0):  # closet shelving with hanging rod
    return [*shelving(w, d, h, n=3), B(-w/2+0.03, w/2-0.03, 1.7, 1.73, -0.015, 0.015, 'furniture-wood')]

def workbench(w, d):
    return [B(-w/2, w/2, 0.86, 0.91, -d/2, d/2, 'furniture-wood'), *legs(w, d, 0.86, t=0.07),
            B(-w/2+0.05, w/2-0.05, 0.15, 0.18, -d/2+0.05, d/2-0.05, 'furniture-wood')]

def rug(w, d):
    return [B(-w/2, w/2, 0, 0.012, -d/2, d/2, 'furniture-upholstery')]

def lounge(w=0.7, d=0.85):
    m = 'furniture-outdoor'
    return [*legs(w, d, 0.35, t=0.05, mat=m), B(-w/2, w/2, 0.35, 0.42, -d/2, d/2, m),
            B(-w/2, w/2, 0.42, 0.85, -d/2, -d/2+0.07, m),
            B(-w/2, -w/2+0.06, 0.42, 0.62, -d/2, d/2, m), B(w/2-0.06, w/2, 0.42, 0.62, -d/2, d/2, m)]

def outdoor_bench(w, d):
    m = 'furniture-outdoor'
    return [*legs(w, d, 0.4, t=0.06, mat=m), B(-w/2, w/2, 0.4, 0.45, -d/2, d/2, m)]

# ---------- layout: (name, room, builder, world bbox x0,x1,z0,z1, facing, tall) ----------
# facing = direction the front of the piece points. Builders get (w, d) in the piece's own frame.
L = []
def put(name, room, fn, x0, x1, z0, z1, facing, overlap_ok=False):
    L.append(dict(name=name, room=room, fn=fn, bbox=(x0, x1, z0, z1), facing=facing, overlap_ok=overlap_ok))

def dims(x0, x1, z0, z1, facing):
    return (x1-x0, z1-z0) if facing in ('+z', '-z') else (z1-z0, x1-x0)

# Primary bedroom (room 03)
put('primary-bed', '03', bed, -5.28, -3.15, -9.63, -7.70, '+x')
put('primary-nightstand-1', '03', casegood, -5.26, -4.81, -10.18, -9.68, '+x')
put('primary-nightstand-2', '03', casegood, -5.26, -4.81, -7.65, -7.15, '+x')
put('primary-bench', '03', (lambda w, d: [*legs(w, d, 0.42, t=0.05), B(-w/2, w/2, 0.42, 0.48, -d/2, d/2, 'furniture-upholstery')]),
    -3.05, -2.65, -9.26, -8.06, '+x')
put('primary-dresser', '03', casegood, -0.82, -0.34, -9.75, -8.25, '-x')
put('primary-armchair', '03', sofa, -1.75, -0.95, -10.78, -9.98, '+z')
# Walk-in closet (room 08)
put('walkin-shelving-west', '08', wardrobe, -5.27, -4.67, -3.00, -0.80, '+x')
put('walkin-shelving-north', '08', wardrobe, -4.55, -2.62, -1.36, -0.78, '-z')
put('walkin-shelving-east', '08', wardrobe, -3.18, -2.58, -3.00, -1.45, '-x')
# Bedroom 2 (room 05) + closet (room 14)
put('bed2-bed', '05', bed, -3.59, -1.57, -0.16, 1.36, '-x')
put('bed2-nightstand-1', '05', casegood, -2.06, -1.58, -0.63, -0.20, '-x')
put('bed2-nightstand-2', '05', casegood, -2.06, -1.58, 1.39, 1.77, '-x')
put('bed2-dresser', '05', casegood, -4.40, -3.20, 2.31, 2.76, '-z')
put('bed2-desk', '05', table, -5.27, -4.72, 0.30, 1.50, '+x')
put('bed2-desk-chair', '05', chair, -4.70, -4.22, 0.65, 1.13, '-x')
put('bed2-closet-shelving', '14', wardrobe, -5.27, -4.13, 3.88, 4.41, '-z')
# Bedroom 3 (room 06) + closet (room 18)
put('bed3-bed', '06', bed, 2.05, 3.96, 0.22, 1.59, '+x')
put('bed3-nightstand-1', '06', casegood, 2.05, 2.50, -0.28, 0.17, '+x')
put('bed3-nightstand-2', '06', casegood, 2.05, 2.50, 1.64, 2.09, '+x')
put('bed3-dresser', '06', casegood, 4.72, 5.19, 1.05, 2.15, '-x')
put('bed3-closet-shelving', '18', wardrobe, 3.64, 5.19, -0.63, -0.25, '+z')
# Bedroom 4 (room 04) + closet (room 19)
put('bed4-bed', '04', bed, 3.17, 5.19, 8.24, 9.76, '-x')
put('bed4-nightstand-1', '04', casegood, 4.74, 5.19, 7.74, 8.19, '-x')
put('bed4-nightstand-2', '04', casegood, 4.74, 5.19, 9.81, 10.26, '-x')
put('bed4-dresser', '04', casegood, 2.22, 2.67, 8.40, 9.60, '+x')
put('bed4-desk', '04', table, 2.25, 3.20, 10.26, 10.81, '-z')
put('bed4-desk-chair', '04', chair, 2.49, 2.97, 9.78, 10.23, '+z')
put('bed4-closet-shelving', '19', wardrobe, 4.84, 5.19, 6.08, 7.26, '-x')
# Garage (room 02)
put('garage-workbench', '02', workbench, -4.40, -2.60, 4.54, 5.14, '+z')
put('garage-shelving', '02', shelving, -5.27, -4.82, 5.60, 8.00, '+x')
# Front porch (room 11) and back porch (room 07)
put('front-porch-bench', '11', outdoor_bench, 0.72, 1.17, 8.60, 9.80, '+x')
put('back-porch-lounge-1', '07', lounge, 2.20, 2.90, -10.15, -9.30, '-z')
put('back-porch-side-table', '07', lambda w, d: table(w, d, 0.5, 'furniture-outdoor'), 3.05, 3.50, -9.95, -9.50, '-z')
put('back-porch-lounge-2', '07', lounge, 3.65, 4.35, -10.15, -9.30, '-z')
# Great room (room 01): island stools, dining, living, foyer
for i, zc in enumerate((-4.25, -3.60, -2.95)):
    put(f'island-stool-{i+1}', '01', stool, 0.22, 0.62, zc-0.2, zc+0.2, '-x')
put('dining-table', '01', table, 2.95, 3.85, -3.80, -2.00, '+z')
for i, (zc) in enumerate((-3.35, -2.45)):
    put(f'dining-chair-w{i+1}', '01', chair, 2.38, 2.88, zc-0.225, zc+0.225, '+x')
    put(f'dining-chair-e{i+1}', '01', chair, 3.92, 4.42, zc-0.225, zc+0.225, '-x')
put('dining-chair-s', '01', chair, 3.175, 3.625, -4.37, -3.87, '+z')
put('dining-chair-n', '01', chair, 3.175, 3.625, -1.93, -1.43, '-z')
put('living-rug', '01', rug, 2.20, 4.40, -7.55, -5.85, '+z', overlap_ok=True)
put('living-sofa', '01', sofa, 1.50, 2.45, -7.80, -5.60, '+x')
put('living-coffee-table', '01', lambda w, d: table(w, d, 0.42), 2.90, 3.50, -7.20, -6.20, '+x')
put('living-media-console', '01', lambda w, d: casegood(w, d, 0.55), 4.74, 5.19, -7.60, -5.80, '-x')
put('living-armchair', '01', sofa, 3.30, 4.15, -8.88, -8.03, '+z')
put('living-bookshelf', '01', lambda w, d: shelving(w, d, 1.8), -0.19, 0.16, -8.00, -6.80, '+x')
put('foyer-console', '01', lambda w, d: casegood(w, d, 0.8), 0.72, 1.07, 4.90, 6.00, '+x')
put('foyer-bench', '01', lambda w, d: [*legs(w, d, 0.42), B(-w/2, w/2, 0.42, 0.47, -d/2, d/2, 'furniture-wood')],
    2.86, 3.21, 4.70, 5.90, '-x')

ROOM_TYPES = {'01': 'great room (kitchen, dining, living, foyer, hall)', '02': 'garage', '03': 'primary bedroom',
              '04': 'bedroom', '05': 'bedroom', '06': 'bedroom', '07': 'back porch', '08': 'walk-in closet',
              '09': 'primary bathroom', '10': 'shared bathroom', '11': 'front porch', '12': 'laundry',
              '13': 'hall bathroom', '14': 'closet', '15': 'pantry', '16': 'linen closet', '17': 'toilet room',
              '18': 'closet', '19': 'closet', '20': 'closet', '21': 'coat closet'}
# Reach-in closets are too shallow for an inward swing, so their doors are assumed to open out.
REACH_IN_CLOSETS = {'14', '18', '19'}
YAW = {'+z': 0, '+x': 90, '-z': 180, '-x': 270}

def box_tris(x0, x1, y0, y1, z0, z1):
    v = np.array([[x, y, z] for x in (x0, x1) for y in (y0, y1) for z in (z0, z1)], dtype=np.float32)
    faces = [((0, 1, 3, 2), (-1, 0, 0)), ((4, 6, 7, 5), (1, 0, 0)), ((0, 4, 5, 1), (0, -1, 0)),
             ((2, 3, 7, 6), (0, 1, 0)), ((0, 2, 6, 4), (0, 0, -1)), ((1, 5, 7, 3), (0, 0, 1))]
    P, N = [], []
    for (a, b, c, d), n in faces:
        for t in ((a, b, c), (a, c, d)):
            P += [v[i] for i in t]; N += [n]*3
    return np.array(P, np.float32), np.array(N, np.float32)

def footprint(j, Bin, mesh_i, t=(0, 0, 0)):
    tris = acc(j, Bin, j['meshes'][mesh_i]['primitives'][0]['attributes']['POSITION']).reshape(-1, 3, 3)
    polys = [Polygon(tr[:, [0, 2]] + [t[0], t[2]]) for tr in tris]
    return unary_union([p.buffer(0) for p in polys if p.area > 1e-6])

def main(src, dst):
    j, Bin = load(src)
    nodes = {n['name']: n for n in j['nodes']}
    rooms = {n['name'][-2:]: footprint(j, Bin, n['mesh']) for n in j['nodes'] if n['extras']['layer'] == 'FLOORS'}
    # obstacles: door swing zones (0.85 m each side), windows (keep tall pieces 0.3 m off), kitchen fixtures
    doors, windows, kitchen = [], [], []
    for n in j['nodes']:
        layer = n['extras']['layer']
        if layer not in ('DOORS', 'WINDOWS', 'KITCHEN'):
            continue
        a = j['accessors'][j['meshes'][n['mesh']]['primitives'][0]['attributes']['POSITION']]
        (x0, _, z0), (x1, _, z1) = a['min'], a['max']
        if layer == 'KITCHEN':
            kitchen.append((n['name'], sbox(x0, z0, x1, z1)))
        elif layer == 'DOORS':
            g = sbox(x0, z0-0.85, x1, z1+0.85) if x1-x0 > z1-z0 else sbox(x0-0.85, z0, x1+0.85, z1)
            doors.append((n['name'], g))
        else:
            windows.append((n['name'], sbox(x0, z0, x1, z1).buffer(0.3)))
    errors, placed = [], []
    for it in L:
        x0, x1, z0, z1 = it['bbox']
        fp = sbox(x0, z0, x1, z1)
        w, d = dims(x0, x1, z0, z1, it['facing'])
        parts = it['fn'](w, d)
        tall = max(p[3] for p in parts) > 0.9
        if not rooms[it['room']].buffer(0.005).contains(fp):
            errors.append(f"{it['name']}: outside room {it['room']}")
        for nm, g in doors:
            if fp.intersection(g).area > 1e-4 and not it['overlap_ok'] and it['room'] not in REACH_IN_CLOSETS:
                errors.append(f"{it['name']}: blocks {nm} swing")
        for nm, g in kitchen:
            if fp.intersection(g).area > 1e-4:
                errors.append(f"{it['name']}: overlaps {nm}")
        if tall:
            for nm, g in windows:
                if fp.intersection(g).area > 1e-4:
                    errors.append(f"{it['name']}: tall piece in front of {nm}")
        for other in placed:
            if not (it['overlap_ok'] or other['overlap_ok']) and fp.intersection(other['fp']).area > 1e-4:
                errors.append(f"{it['name']}: overlaps {other['name']}")
        it['fp'], it['parts'] = fp, parts
        placed.append(it)
    if errors:
        print('\n'.join(errors)); sys.exit(1)

    # ---------- write ----------
    mat_idx = {m['name']: i for i, m in enumerate(j['materials'])}
    blob = bytearray(Bin)
    def add_view(arr, target=34962):
        while len(blob) % 4: blob.append(0)
        off = len(blob); data = arr.astype(np.float32).tobytes(); blob.extend(data)
        j['bufferViews'].append(dict(buffer=0, byteOffset=off, byteLength=len(data), target=target))
        return len(j['bufferViews']) - 1
    for it in placed:
        prims = []
        for mat in dict.fromkeys(p[6] for p in it['parts']):
            Ps, Ns = zip(*[box_tris(*p[:6]) for p in it['parts'] if p[6] == mat])
            P, N = np.concatenate(Ps), np.concatenate(Ns)
            pa = len(j['accessors'])
            j['accessors'].append(dict(bufferView=add_view(P), componentType=5126, count=len(P), type='VEC3',
                                       min=P.min(0).round(4).tolist(), max=P.max(0).round(4).tolist()))
            j['accessors'].append(dict(bufferView=add_view(N), componentType=5126, count=len(N), type='VEC3'))
            prims.append(dict(attributes=dict(POSITION=pa, NORMAL=pa+1), material=mat_idx[mat], mode=4))
        j['meshes'].append(dict(name=it['name'], primitives=prims))
        x0, x1, z0, z1 = it['bbox']; th = math.radians(YAW[it['facing']])
        node = dict(name=it['name'], mesh=len(j['meshes'])-1, translation=[round((x0+x1)/2, 4), 0, round((z0+z1)/2, 4)],
                    extras=dict(layer='FURNITURE', units='meters', room=f"room-floor-{it['room']}"))
        if th:
            node['rotation'] = [0, round(math.sin(th/2), 6), 0, round(math.cos(th/2), 6)]
        j['nodes'].append(node)
        j['scenes'][0]['nodes'].append(len(j['nodes'])-1)
    for n in j['nodes']:
        if n['extras']['layer'] == 'FLOORS':
            n['extras']['roomType'] = ROOM_TYPES[n['name'][-2:]]
            n['extras']['roomTypeInferred'] = True
    j['buffers'][0]['byteLength'] = len(blob)
    j['asset']['extras']['geometryCounts']['furniture'] = len(placed)
    j['scenes'][0]['name'] = 'Prism furnished floor plan'
    js = json.dumps(j, separators=(',', ':')).encode()
    js += b' ' * (-len(js) % 4)
    while len(blob) % 4: blob.append(0)
    out = struct.pack('<4sII', b'glTF', 2, 12 + 8 + len(js) + 8 + len(blob))
    out += struct.pack('<I4s', len(js), b'JSON') + js + struct.pack('<I4s', len(blob), b'BIN\0') + bytes(blob)
    open(dst, 'wb').write(out)
    print(f'wrote {dst}: {len(placed)} furniture pieces, {len(out)} bytes')

if __name__ == '__main__':
    main(sys.argv[1], sys.argv[2])
