# Frozen pre-P4 predicates; see README.md for provenance.
def inside_landmark(x, y):
    return inside_site(x - SPORTS_X, y - SPORTS_Y) or any((abs(x - sx) < 3 and abs(y - sy) < 3 and inside_mall(identity, x - sx, y - sy) for (identity, (sx, sy)) in MALL_ORIGINS.items())) or inside_tingzi(x - TINGZI_X, y - TINGZI_Y) or inside_changyou(x - CHANGYOU_X, y - CHANGYOU_Y) or any((abs(x - sx) < 7 and abs(y - sy) < 7 and inside_station(identity, x - sx, y - sy) for (identity, (sx, sy, _)) in STATION_SITES.items())) or any((abs(x - cx) < width / 2 and abs(y - cy) < depth / 2 for (cx, cy, width, depth) in CLEAR_AREAS))

def old_visible(b, building_index):
    if building_index in RAILWAY_BUILDINGS:
        return False
    if any((n in b.get('name', '') for n in ['龙象塔', '华润大厦A', '地王国际商会中心'])):
        return False
    ring = b['rings'][0][:-1]
    if len(ring) < 3:
        return False
    x = sum((p[0] for p in ring)) / len(ring)
    y = sum((p[1] for p in ring)) / len(ring)
    if inside_landmark(x, y):
        return False
    if any((abs(x - sx) < 5 and abs(y - sy) < 5 and intersects_mall(identity, ring, sx, sy) for (identity, (sx, sy)) in MALL_ORIGINS.items())):
        return False
    return True
