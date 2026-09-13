"""Create the complete Nanning scene and editable .blend with Blender 5.2.1.
Run: blender --background --python blender/build_city.py
Data preparation uses WGS84; Blender uses X east, Y north, Z up.
glTF converts to Three.js X east, Y up, Z south on export.
"""
import bpy
import hashlib
import gzip
import json
import math
import random
import sys
from pathlib import Path
from mathutils import Vector
from mathutils.geometry import tessellate_polygon

ROOT = Path(__file__).resolve().parents[1]
MINZU_CONTEXT_ONLY = '--minzu-context' in sys.argv
TERRAIN_CONTEXT_ONLY = '--terrain-context' in sys.argv
if '--site-access-plan' in sys.argv and any(flag in sys.argv for flag in
        ['--terrain-context','--minzu-context','--capture-road-inputs','--check-road-interfaces']):
    raise ValueError('Site access is downstream of resolved roads; prepare road contexts without --site-access-plan')
sys.path.insert(0, str(ROOT / 'blender'))
from extra_landmarks import build_extra_landmarks
from terrain_height import scene_height
from gltf_export import export_city
from landmark_details import build_expo, build_bridge
from expo_landmark import site_distance as expo_site_distance
from sports_landmark import SITE_PADS, MATERIAL_KEYS as SPORTS_MATERIALS, pad_distance, inside_site
from tingzi_landmark import MATERIAL_KEYS as TINGZI_MATERIALS, inside_site as inside_tingzi, terrace_level
from bridge_landmark import MATERIAL_KEYS as BRIDGE_MATERIALS
from major_bridges import PLAN as RIVER_BRIDGE_PLAN, SPECS as RIVER_BRIDGE_SPECS
from major_bridges import MATERIALS as RIVER_BRIDGE_MATS, MATERIAL_KEYS as RIVER_BRIDGE_KEYS
from major_bridges import REPLACED_ROADS as RIVER_BRIDGE_ROADS, Bridge as RiverBridge
from major_bridges import build_structure as build_river_bridge, build_details as build_river_details
from changyou_landmark import build_changyou, MATERIAL_KEYS as CHANGYOU_MATERIALS, inside_site as inside_changyou
from nanhu_landmark import build_nanhu, MATERIAL_KEYS as NANHU_MATERIALS, inside_park as inside_nanhu
from nanhu_landmark import shore_height as nanhu_shore_height, replaces_terrain_cell, build_park_terrain
from forest_canopy import PLAN as FOREST_PLAN, REGIONS as FOREST_REGIONS, REPLACED as FOREST_REPLACED, MOUNTAIN_REMOVED
from forest_canopy import build_canopy, build_crown_clusters, terrain_surface, refined_terrain_height, CANOPY_MATERIALS
from forest_canopy import coarse_terrain_surface, canopy_factor
from terrain_mesh import build as build_terrain_mesh
from terrain_reduction_runtime import configure as configure_terrain_reduction, apply_existing as apply_terrain_reduction
from site_access_runtime import configure as configure_site_access, apply_active as apply_site_access, append_roads as append_site_access_roads
from building_placement import prepared as prepared_building, envelope as building_envelope, render as render_prepared_building
from building_placement import validate_road_envelope
from mountain_terrain import PLAN as MOUNTAIN_PLAN, PATH_KEYS as PARK_PATH_KEYS
from mountain_terrain import contains as inside_mountain, replaces_cell as replaces_mountain_cell, build as build_mountain_terrain, build_paths as build_mountain_paths, water_level as mountain_water_level
from local_terrain import PLAN as WATERFRONT_PLAN, MATERIAL_KEYS as TERRAIN_MATERIALS
from local_terrain import contains as inside_local_terrain, replaces_cell as replaces_local_cell, build as build_local_terrain
from site_grading import PLAN as GRADING_PLAN, MATERIAL_KEYS as GRADING_MATERIALS, contains as inside_grading
TERRAIN_MATERIALS=TERRAIN_MATERIALS+(GRADING_MATERIALS if GRADING_PLAN is not None else [])
from reservoir_runtime import PLAN as RESERVOIR_PLAN, MATERIAL_KEYS as RESERVOIR_MATERIALS
from reservoir_runtime import contains as inside_reservoir, water_level as reservoir_water_level, dedicated_dam
from reservoir_runtime import custom_water_contains, custom_water_triangles, build_water_controls
TERRAIN_MATERIALS=TERRAIN_MATERIALS+(RESERVOIR_MATERIALS if RESERVOIR_PLAN is not None else [])
from vegetation import build_tree
from zhuxi_interchange import build_details as build_zhuxi_details, build_greenery as build_zhuxi_greenery, MATERIAL_KEYS as ZHUXI_MATERIALS
from station_landmarks import PLAN as STATION_PLAN, STATIONS, MATERIAL_KEYS as STATION_MATERIALS
from station_landmarks import inside_site as inside_station, ground_blend as station_ground_blend
from zhenning_landmark import build_zhenning, MATERIAL_KEYS as ZHENNING_MATERIALS, terrace_level as zhenning_terrace_level
from zhenning_landmark import terrain_patch as zhenning_terrain_patch
from landmark_sites import SPECS as CALIBRATION, inside_site as inside_calibrated_site
from confucius_landmark import MATERIALS as TEMPLE_MATERIALS
from landmark_vegetation import SETTINGS as LANDMARK_VEGETATION, canopy_factor as landmark_canopy_factor
from diwang_landmark import build_diwang
from mall_landmarks import PLAN as MALL_PLAN, SITES as MALL_SITES, MATERIALS as MALL_MATS
from mall_landmarks import build_mall, inside_site as inside_mall, intersects_site as intersects_mall
from mall_landmarks import support_level as mall_support_level
from cultural_landmarks import SPECS as CULTURAL_SPECS, MATERIALS as CULTURAL_MATS
from cultural_landmarks import build_cultural, support_level as cultural_support_level
from viaduct import PLAN as VIADUCT_PLAN, MATERIAL_KEYS as VIADUCT_MATERIALS, REMOVED_TREES as VIADUCT_TREES
from viaduct import Viaduct, build_structure as build_viaduct_structure, build_details as build_viaduct_details
from railways import PLAN as RAILWAY_PLAN, MATERIAL_KEYS as RAILWAY_MATERIALS, Railways
from railways import REMOVED_TREES as RAILWAY_TREES, REMOVED_BUILDINGS as RAILWAY_BUILDINGS
from railways import build_structure as build_railway_structure, build_details as build_railway_details
from minzu_avenue import PLAN as MINZU_PLAN, MATERIAL_KEYS as MINZU_MATERIALS, MinzuAvenue
from minzu_avenue import REPLACED_ROADS as MINZU_ROADS, REMOVED_TREES as MINZU_TREES
from road_interfaces import build_structure as build_minzu_structure, build_details as build_minzu_details
from ground_roads import PLAN as GROUND_ROAD_PLAN, PLAN_HASH as GROUND_ROAD_HASH, MATERIAL_KEYS as GROUND_ROAD_MATERIALS
from ground_roads import REPLACED_ROADS as GROUND_ROADS, REMOVED_TREES as GROUND_ROAD_TREES, build_ground_roads
from elevated_roads import PLAN as ELEVATED_PLAN, PLAN_HASH as ELEVATED_HASH, REPLACED_ROADS as ELEVATED_ROADS, ElevatedRoads
from elevated_roads import build_structure as build_elevated_structure, build_details as build_elevated_details
GEO = json.loads((ROOT / 'public/data/geography.json').read_text())
DEM = json.loads((ROOT / 'public/data/terrain.json').read_text())
CATALOG = json.loads((ROOT / 'data/landmarks.json').read_text())
PLACE_BY_ID = {place['id']: place for place in CATALOG}
for path,digest in MOUNTAIN_PLAN['inputHashes'].items():
    assert hashlib.sha256((ROOT/path).read_bytes()).hexdigest()==digest, f'Rebuild mountain after changing {path}'
for path,digest in WATERFRONT_PLAN['inputHashes'].items():
    assert hashlib.sha256((ROOT/path).read_bytes()).hexdigest()==digest, f'Rebuild waterfront after changing {path}'
for block in GEO.get('urbanBlocks', []):
    assert hashlib.sha256((ROOT/block['sourceFile']).read_bytes()).hexdigest()==block['sourceHash'], 'Rebuild the residential plan after changing its source/template'
assert MALL_PLAN['sceneCenter'] == GEO['center']
assert MALL_PLAN['sourceHash'] == hashlib.sha256((ROOT/'data/malls-source.json').read_bytes()).hexdigest(), 'Rebuild the mall plan after changing source geometry'
assert all([PLACE_BY_ID[k]['lon'], PLACE_BY_ID[k]['lat']] == v['center'] for k,v in MALL_SITES.items())
assert VIADUCT_PLAN['sceneCenter'] == GEO['center']
assert RIVER_BRIDGE_PLAN['sceneCenter'] == GEO['center']
for path, fingerprint in RIVER_BRIDGE_PLAN['inputHashes'].items():
    assert hashlib.sha256((ROOT/path).read_bytes()).hexdigest() == fingerprint, f'Rebuild bridges after changing {path}'
for path, fingerprint in VIADUCT_PLAN['inputHashes'].items():
    assert hashlib.sha256((ROOT/path).read_bytes()).hexdigest() == fingerprint, f'Rebuild the viaduct plan after changing {path}'
assert STATION_PLAN['sceneCenter'] == GEO['center'], 'Rebuild the station plan for the scene origin'
assert STATION_PLAN['sourceHash'] == hashlib.sha256((ROOT/'data/stations-source.json').read_bytes()).hexdigest(), 'Rebuild the station plan after changing railway data'
for path,fingerprint in RAILWAY_PLAN['inputHashes'].items():
    assert hashlib.sha256((ROOT/path).read_bytes()).hexdigest()==fingerprint, f'Rebuild the railway plan after changing {path}'
for path, fingerprint in MINZU_PLAN['inputHashes'].items():
    assert hashlib.sha256((ROOT/path).read_bytes()).hexdigest() == fingerprint, f'Rebuild the Minzu plan after changing {path}'
for path, fingerprint in ({} if MINZU_CONTEXT_ONLY or TERRAIN_CONTEXT_ONLY else GROUND_ROAD_PLAN['inputHashes']).items():
    assert hashlib.sha256((ROOT/path).read_bytes()).hexdigest() == fingerprint, f'Rebuild ground roads after changing {path}'
for path, fingerprint in ({} if MINZU_CONTEXT_ONLY or TERRAIN_CONTEXT_ONLY else ELEVATED_PLAN['inputHashes']).items():
    assert hashlib.sha256((ROOT/path).read_bytes()).hexdigest() == fingerprint, f'Rebuild elevated roads after changing {path}'
MINX, MINY, MAXX, MAXY = GEO['bounds']
assert FOREST_PLAN['center'] == GEO['center'] and FOREST_PLAN['bbox'] == GEO['bbox'], 'Rebuild the forest plan for the current city extent'
for path, fingerprint in FOREST_PLAN['inputHashes'].items():
    assert hashlib.sha256((ROOT/path).read_bytes()).hexdigest() == fingerprint, f'Rebuild the forest plan after changing {path}'
COLS, ROWS = DEM['cols'], DEM['rows']
HEIGHTS = DEM.get('sceneHeights', DEM['heights'])
LANDCOVER = DEM.get('landcover', [0]*(COLS*ROWS))
SCALE_Z = DEM.get('verticalExaggeration',3.0)
RNG = random.Random(771)

bpy.ops.object.select_all(action='SELECT')
bpy.ops.object.delete(use_global=False)
for block in list(bpy.data.materials):
    bpy.data.materials.remove(block)


def srgb(v):
    return v / 12.92 if v <= .04045 else ((v + .055) / 1.055) ** 2.4


def material(name, color, roughness=.85, metallic=0):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    c = tuple(srgb(int(color[i:i+2], 16) / 255) for i in (0, 2, 4)) + (1,)
    m.diffuse_color = c
    bsdf = m.node_tree.nodes.get('Principled BSDF')
    bsdf.inputs['Base Color'].default_value = c
    bsdf.inputs['Roughness'].default_value = roughness
    bsdf.inputs['Metallic'].default_value = metallic
    return m

MATS = {
    'ground': material('Porcelain earth', 'ced8c8'),
    'hill': material('Green hills', '719784'),
    'hillLight': material('Hill facets light', '86a08a'),
    'bank': material('Riverbank', 'b3cbb5'),
    'base': material('Cut earth', '607e74'),
    'water': material('Jade water', '3ca49b', .27, .22),
    'park_walk': material('Qingxiu park footway', 'd5cdb8'),
    'park_steps': material('Qingxiu stepped path', 'c8b897'),
    'park_service': material('Qingxiu park service road', '8f9c8e'),
    'park_edge': material('Qingxiu path edge', 'b4b7a5'),
    'waterfront_paving': material('Riverside promenade stone', 'd6d6c5'),
    'waterfront_wall': material('Riverside retaining stone', 'a9b5a5'),
    'road': material('Road white', 'eeeee1'),
    'highway': material('Main avenue', 'f4e4b9'),
    'building': material('Warm porcelain', 'e8e9df'),
    'building2': material('Cool porcelain', 'cededb'),
    'building3': material('Sandstone porcelain', 'd9ddce'),
    'roof': material('Roof', 'f7f3e8'),
    'leaf': material('Canopy deep', '387b63'),
    'leaf2': material('Canopy jade', '529176'),
    'leaf3': material('Canopy lime', '83a077'),
    'trunk': material('Tree trunk', '637667'),
    'zhenning_stone': material('Zhenning weathered red sandstone', '927668', .94),
    'zhenning_stone_light': material('Zhenning pale sandstone blocks', 'ab9682', .94),
    'zhenning_stone_dark': material('Zhenning shaded sandstone', '71685b', .95),
    'zhenning_mortar': material('Zhenning deep masonry joints', '494940', .98),
    'zhenning_concrete': material('Zhenning ivory concrete gallery', 'dfdfcf', .87),
    'zhenning_paving': material('Zhenning warm stone paving', 'bcbba9', .92),
    'zhenning_iron': material('Zhenning historic dark iron', '49433a', .64, .34),
    'zhenning_bronze': material('Zhenning aged bronze fittings', '79735c', .72, .30),
    'zhenning_wood': material('Zhenning dark red doors', '69493e', .86),
    'zhenning_red': material('Zhenning red inscription', 'a45242', .86),
    'forest_deep': material('Forest shaded foliage', '537f68'),
    'forest_jade': material('Forest jade foliage', '608b71'),
    'forest_light': material('Forest sunlit foliage', '70967b'),
    'landmark': material('Landmark jade glass', '568f87', .28, .35),
    'accent': material('Brass accent', 'd3ae6b', .4, .2),
    'bridge': material('Bridge vermilion', 'b9654c', .65),
    'expo_membrane': material('Expo ivory membrane', 'f8f7ef', .64),
    'expo_glass': material('Expo silver sage glazing', '91b0aa', .24, .18),
    'expo_frame': material('Expo aluminium frames', 'b5bfb9', .42, .3),
    'expo_stone': material('Expo limestone terraces', 'd2d5ca'),
    'arts_white': material('Arts folded white aluminium', 'f4f5ee', .48, .08),
    'arts_shell': material('Arts recessed silver roof', 'b9c4be', .57, .10),
    'arts_soffit': material('Arts pearl canopy soffit', 'dfe4dc', .72),
    'arts_glass': material('Arts grey green foyer glazing', '68857f', .22, .23),
    'arts_frame': material('Arts brushed aluminium frames', 'a9b8b0', .36, .35),
    'arts_stone': material('Arts pale stone podium', 'd8dacc', .9),
    'sports_roof': material('Sports silver leaf roof', 'e0e7e3', .42, .28),
    'sports_soffit': material('Sports roof underside', 'a2afa9', .72, .12),
    'sports_frame': material('Sports steel structure', '98a8a1', .42, .32),
    'sports_glass': material('Sports sage glazing', '52766e', .25, .24),
    'sports_stone': material('Sports concrete terraces', 'd6d9cd', .85),
    'sports_track': material('Sports terracotta track', 'ae6453', .90),
    'sports_turf': material('Sports pitch deep green', '418367', .95),
    'sports_turf_light': material('Sports pitch mown green', '559573', .95),
    'sports_line': material('Sports field markings', 'f4f2e3', .90),
    'sports_seat_red': material('Sports terracotta seating', 'b76c51', .70),
    'sports_seat_gold': material('Sports amber seating', 'd3af68', .70),
    'sports_screen': material('Sports scoreboard', '233f3c', .40),
    'tingzi_wall': material('Tingzi warm ivory facade', 'e6decb', .82),
    'tingzi_trim': material('Tingzi white limestone mouldings', 'f8f2e5', .73),
    'tingzi_glass': material('Tingzi recessed arched glazing', '526563', .28, .12),
    'tingzi_roof': material('Tingzi terracotta spires', 'a65b42', .70),
    'tingzi_dome': material('Tingzi blue grey dome', '64848b', .46, .18),
    'tingzi_paving': material('Tingzi terrace stone', 'c9c9b9', .88),
    'tingzi_deck': material('Tingzi passenger pier decking', '918672', .85),
    'nbridge_steel': material('Nanning Bridge vermilion steel box ribs', 'b95139', .47, .28),
    'nbridge_edge': material('Nanning Bridge pale edge beams', 'd4d8cf', .75),
    'nbridge_road': material('Nanning Bridge asphalt deck', '727e78', .92),
    'nbridge_concrete': material('Nanning Bridge concrete supports', 'c3c8bc', .86),
    'nbridge_cable': material('Nanning Bridge steel cables and rails', '7b8981', .45, .42),
    'nbridge_line': material('Nanning Bridge road markings', 'eee9cf', .80),
    'changyou_tile': material('Changyou grey curved roof tiles', '69716a', .82),
    'changyou_tile_rib': material('Changyou raised tile ridges', '899187', .80),
    'changyou_eave': material('Changyou ochre eave trim', 'bc9f6d', .78),
    'changyou_wood': material('Changyou vermilion timber', '8c493a', .77),
    'changyou_dark': material('Changyou recessed timber walls', '514b3d', .83),
    'changyou_stone': material('Changyou pale stone colonnade', 'dfdccb', .86),
    'changyou_window': material('Changyou shaded glazing', '4c6960', .32, .12),
    'nanhu_stone': material('Nanhu white concrete arches', 'd9dcd2', .86),
    'nanhu_cap': material('Nanhu pale balustrade', 'f0eee1', .80),
    'nanhu_paving': material('Nanhu warm stone paths', 'cbbfaa', .88),
    'nanhu_edge': material('Nanhu grey stone edging', 'a4afa1', .90),
    'nanhu_grass': material('Nanhu causeway grass', '8ba674', .95),
    'nanhu_wood': material('Nanhu boardwalk timber', '927c59', .89),
    'nanhu_trunk': material('Nanhu tree trunks', '7c7158', .92),
    'nanhu_palm': material('Nanhu palm fronds', '507c47', .88),
    'nanhu_leaf': material('Nanhu broadleaf canopy', '62895a', .90),
    'nanhu_leaf_light': material('Nanhu sunlit foliage', '91aa6e', .92),
    'nanhu_leaf_dark': material('Nanhu shaded foliage', '477958', .91),
    'nanhu_metal': material('Nanhu garden fittings', '52675c', .62, .18),
    'station_stone': material('Station pale limestone', 'e2ddcb', .76),
    'station_paving': material('Station platform paving', 'c7cdc4', .86),
    'station_roof': material('Station silver roof panels', 'e9eeea', .43, .24),
    'station_soffit': material('Station shaded steel soffits', '9eafa6', .68, .16),
    'station_glass': material('Station sage curtain wall', '5a8d85', .26, .26),
    'station_frame': material('Station aluminium mullions', 'a3b5ae', .40, .35),
    'station_rail': material('Station rails and clock hands', '526461', .43, .36),
    'station_ballast': material('Station track ballast', '89938a', .96),
    'station_red': material('Station vermilion lettering', 'b7473b', .65),
    'station_line': material('Station clock face and safety lines', 'e7dcb0', .77),
    'station_blue': material('Nanning entrance shelter', '4d96a4', .53, .16),
    'viaduct_concrete': material('Qingxiang warm concrete', 'd8dbcf', .87),
    'viaduct_soffit': material('Qingxiang shaded box girders', 'a6b5a9', .88),
    'viaduct_asphalt': material('Qingxiang sage asphalt', '71837b', .95),
    'viaduct_line': material('Qingxiang lane markings', 'f1ead3', .90),
    'viaduct_metal': material('Qingxiang lamp columns', '7d9690', .53, .20),
    'road_secondary': material('Secondary sage streets', '91a093', .97),
    'road_local': material('Simple neighbourhood paving', 'b5beac', .99),
    'rail_ballast': material('Railway grey ballast', '68766e', .96),
    'rail_steel': material('Railway polished rail heads', 'e0e3db', .55, .25),
    'rail_sleeper': material('Railway concrete sleepers', 'd4d1be', .94),
    'rail_concrete': material('Railway bridge concrete', 'c3cbbb', .87),
    'rail_metal': material('Railway overhead fittings', '677a70', .56, .32),
    'rail_earth': material('Railway graded earth', 'a5af94', .98),
    'block_paving': material('Shared site paving', 'a4a79a', .96),
    'block_retaining': material('Site retaining earth', '788782', .98),
    'reservoir_ground': material('Reservoir terrain', '617a54', .98),
    'dam_slope': material('Estimated dam embankment', '8c916e', .98),
    'dam_crest': material('Estimated dam crest', 'b3b8a8', .96),
}
MATS.update({key: material(*values) for key, values in RIVER_BRIDGE_MATS.items()})
MATS.update({key: material(*values) for key, values in MALL_MATS.items()})
MATS.update({key: material(*values) for key, values in CULTURAL_MATS.items()})
MATS.update({key: material(*values) for key, values in TEMPLE_MATERIALS.items()})


from scene_ground import SceneGround
GROUND_CONTEXT = SceneGround(GEO, DEM, CATALOG)


def terrain_height(x, y):
    return GROUND_CONTEXT.terrain_height(x, y)


EXPO = PLACE_BY_ID['expo']
EXPO_X = (EXPO['lon']-GEO['center'][0])*1113.2*math.cos(math.radians(GEO['center'][1]))
EXPO_Y = (EXPO['lat']-GEO['center'][1])*1113.2
EXPO_GROUND = terrain_height(EXPO_X, EXPO_Y)
SPORTS = PLACE_BY_ID['sports-center']
SPORTS_X = (SPORTS['lon']-GEO['center'][0])*1113.2*math.cos(math.radians(GEO['center'][1]))
SPORTS_Y = (SPORTS['lat']-GEO['center'][1])*1113.2
SPORTS_LEVELS = [terrain_height(SPORTS_X+pad[0], SPORTS_Y+pad[1]) for pad in SITE_PADS]
NANHU_X = (PLACE_BY_ID['nanhu']['lon']-GEO['center'][0])*1113.2*math.cos(math.radians(GEO['center'][1]))
NANHU_Y = (PLACE_BY_ID['nanhu']['lat']-GEO['center'][1])*1113.2
STATION_SITES = {}
for identity, station in STATIONS.items():
    assert [PLACE_BY_ID[identity]['lon'], PLACE_BY_ID[identity]['lat']] == station['center']
    sx = (station['center'][0]-GEO['center'][0])*1113.2*math.cos(math.radians(GEO['center'][1]))
    sy = (station['center'][1]-GEO['center'][1])*1113.2
    STATION_SITES[identity] = (sx, sy, terrain_height(sx, sy))


def height(x, y):
    return GROUND_CONTEXT(x, y)


base_height = height
railways = Railways(base_height,
    lambda x,y,mobile: terrain_surface(x,y,base_height,GEO['bounds'],COLS,ROWS,mobile),STATION_SITES)
def height(x,y):
    return railways.cut_ground(x,y,base_height(x,y))
railways.ground = height
railways.surface = lambda x,y,mobile: terrain_surface(x,y,height,GEO['bounds'],COLS,ROWS,mobile)

# Native landmark/bridge ground and profile-specific roads/vegetation all query
# the same replacement. The unpatched callback prevents recursive re-blending.
unpatched_height = height
def height(x,y):
    if inside_local_terrain(x,y) or inside_mountain(x,y) or inside_grading(x,y) or inside_reservoir(x,y):
        return terrain_surface(x,y,unpatched_height,GEO['bounds'],COLS,ROWS)
    return unpatched_height(x,y)
height.unpatched = unpatched_height
railways.ground = height
railways.surface = lambda x,y,mobile: terrain_surface(x,y,height,GEO['bounds'],COLS,ROWS,mobile)


def pos(lon,lat):
    x=(lon-GEO['center'][0])*1113.2*math.cos(math.radians(GEO['center'][1]))
    y=(lat-GEO['center'][1])*1113.2
    return x,y,height(x,y)+.1


def displayed_ground_bounds(x,y):
    levels=[height(x,y), *(terrain_surface(x,y,height,GEO['bounds'],COLS,ROWS,profile)
                           for profile in [False,True])]
    return min(levels),max(levels)



from city_visibility import CityVisibility
city_visibility = CityVisibility(GEO, CATALOG)
CLEAR_AREAS = city_visibility.clear_areas
LEGACY_CLEAR_AREAS = city_visibility.legacy_clear_areas
CALIBRATION_ORIGINS = city_visibility.calibration_origins
TINGZI_X, TINGZI_Y = city_visibility.tingzi
CHANGYOU_X, CHANGYOU_Y = city_visibility.changyou
MALL_ORIGINS = city_visibility.mall_origins


def inside_landmark(x, y, legacy=False):
    return city_visibility.inside_landmark(x, y, legacy=legacy)


class Batch:
    def __init__(self, name, keys, spatial=False, weld=False):
        self.name, self.keys, self.v, self.f, self.mi = name, keys, [], [], []
        self.spatial = spatial
        self.weld = weld
        self.normals = []
        self.cells = []
        self.cell_override = None
        self.partitions = []
        self.partition_override = ''
    def face(self, vertices, key, normals=None):
        start = len(self.v)
        self.v.extend(vertices)
        self.f.append(tuple(range(start, start + len(vertices))))
        self.mi.append(self.keys.index(key))
        self.normals.append(normals)
        self.cells.append(self.cell_override)
        self.partitions.append(self.partition_override)
    def box(self, x, y, z, w, d, h, key, roof=None, angle=0):
        verts = []
        for zz in [z, z+h]:
            for xx, yy in [(-w/2,-d/2),(w/2,-d/2),(w/2,d/2),(-w/2,d/2)]:
                verts.append((x+xx*math.cos(angle)-yy*math.sin(angle), y+xx*math.sin(angle)+yy*math.cos(angle), zz))
        for ids in [(0,1,5,4),(1,2,6,5),(2,3,7,6),(3,0,4,7),(4,5,6,7)]:
            self.face([verts[k] for k in ids], roof if ids == (4,5,6,7) and roof else key)
    def cone(self, x, y, z, radius, top_radius, h, key, segments=7):
        lower, upper = [], []
        for i in range(segments):
            a = i/segments*math.tau
            lower.append((x+math.cos(a)*radius,y+math.sin(a)*radius,z))
            upper.append((x+math.cos(a)*top_radius,y+math.sin(a)*top_radius,z+h))
        for i in range(segments):
            k = (i+1)%segments
            self.face([lower[i],lower[k],upper[k],upper[i]],key)
        self.face(upper,key)
    def beam(self, a, b, radius, key):
        axis=Vector(b)-Vector(a)
        if axis.length < .00001: return
        axis.normalize()
        side=axis.cross(Vector((0,0,1)) if abs(axis.z)<.95 else Vector((0,1,0))).normalized()*radius
        up=axis.cross(side).normalized()*radius
        rings=[[tuple(Vector(p)+side*u+up*v) for u,v in [(-1,-1),(1,-1),(1,1),(-1,1)]] for p in [a,b]]
        for i in range(4):
            j=(i+1)%4
            self.face([rings[0][i],rings[0][j],rings[1][j],rings[1][i]],key)
        self.face(rings[0],key);self.face(rings[1],key)
    def finish(self):
        def make_object(name, vertices, faces, materials, parent=None, normals=None):
            mesh=bpy.data.meshes.new(name)
            mesh.from_pydata(vertices, [], faces)
            for key in self.keys: mesh.materials.append(MATS[key])
            for polygon,index in zip(mesh.polygons,materials):
                polygon.material_index=index
                if self.weld:
                    polygon.use_smooth=True
            mesh.update()
            if normals and any(n is not None for n in normals):
                # Smooth along a membrane panel while keeping its fold creases.
                # Zero vectors retain Blender's geometric normals on other faces.
                mesh.normals_split_custom_set([
                    normal for face, custom in zip(faces, normals)
                    for normal in (custom if custom is not None else [(0, 0, 0)] * len(face))
                ])
            obj=bpy.data.objects.new(name,mesh)
            bpy.context.collection.objects.link(obj)
            obj.parent=parent
            return obj
        # Spatial batches permit Three.js frustum culling in close views.
        if not self.spatial and self.name not in ['Terrain','Buildings','Vegetation','Roads','Bridges']:
            return make_object(self.name,self.v,self.f,self.mi,normals=self.normals)
        parent=bpy.data.objects.new(self.name,None)
        bpy.context.collection.objects.link(parent)
        groups={}
        for face,index,normal,forced_cell,partition in zip(self.f,self.mi,self.normals,self.cells,self.partitions):
            verts=[self.v[i] for i in face]
            cx=sum(v[0] for v in verts)/len(verts);cy=sum(v[1] for v in verts)/len(verts)
            cell=forced_cell if forced_cell is not None else (math.floor((cx-MINX)/80),math.floor((cy-MINY)/80))
            vertices,faces,materials,normals,lookup=groups.setdefault((partition,*cell),([],[],[],[],{}))
            if self.weld:
                # Shared canopy vertices must also share Blender's normal
                # space, otherwise tiny custom-normal differences defeat glTF
                # deduplication and encode each triangle corner separately.
                ids=[]
                for vertex in verts:
                    key=tuple(vertex)
                    if key not in lookup:
                        lookup[key]=len(vertices)
                        vertices.append(vertex)
                    ids.append(lookup[key])
                faces.append(tuple(ids))
            else:
                offset=len(vertices);vertices.extend(verts)
                faces.append(tuple(range(offset,offset+len(verts))))
            materials.append(index);normals.append(normal)
        for (partition,i,j),(vertices,faces,materials,normals,lookup) in sorted(groups.items()):
            suffix=f'{partition}_' if partition else ''
            make_object(f'{self.name}_{suffix}{i}_{j}',vertices,faces,materials,parent,normals)
        return parent


def build_forests(parent, lightweight=False):
    for region in FOREST_REGIONS:
        prefix = f'Vegetation_{region["id"]}'
        canopy = Batch(prefix+'_canopy',CANOPY_MATERIALS,spatial=True,weld=True)
        build_canopy(canopy,region,height,GEO['bounds'],COLS,ROWS,lightweight)
        canopy_group = canopy.finish()
        canopy_group.parent = parent
        for obj in canopy_group.children:
            for polygon in obj.data.polygons:
                polygon.use_smooth = True
        crowns = Batch(prefix+'_crowns',CANOPY_MATERIALS,spatial=True)
        build_crown_clusters(crowns,region,height,GEO['bounds'],COLS,ROWS,lightweight)
        crowns.finish().parent = parent


BUILDING_SUPPORT=None
BUILDING_SUPPORT_PATH=None
for argument_index,argument in enumerate(sys.argv[:-1]):
    if argument=='--building-support-plan':
        from building_support_plan import BuildingSupportPlan
        BUILDING_SUPPORT_PATH=Path(sys.argv[argument_index+1]).resolve()
        BUILDING_SUPPORT=BuildingSupportPlan.read(BUILDING_SUPPORT_PATH,ROOT)
if any(prepared_building(b) for b in GEO['buildings']) and BUILDING_SUPPORT is None and not (TERRAIN_CONTEXT_ONLY or MINZU_CONTEXT_ONLY or '--check-road-interfaces' in sys.argv):
    raise ValueError('P5 buildings require --building-support-plan for rendering and road input capture')
for argument_index,argument in enumerate(sys.argv[:-1]):
    if argument=='--terrain-reduction-plan':
        configure_terrain_reduction(globals(),sys.argv[argument_index+1])
for argument_index,argument in enumerate(sys.argv[:-1]):
    if argument=='--site-access-plan':
        configure_site_access(globals(),sys.argv[argument_index+1])

if MINZU_CONTEXT_ONLY:
    # Regenerate connecting streets from the new road, before a full export.
    # This avoids sampling stale Minzu heights/side roads from the previous GLB.
    sample = lambda x,y,mobile: terrain_surface(x,y,height,GEO['bounds'],COLS,ROWS,mobile)
    context_viaduct = Viaduct(height, sample)
    context_minzu = MinzuAvenue(context_viaduct.road_level, sample)
    report = context_minzu.validate()
    faces = []
    for key,path in context_minzu.paths.items():
        if context_minzu.routes[key]['bridge']: continue
        for a,b in zip(context_minzu.sections[key],context_minzu.sections[key][1:]):
            wa,wb = context_minzu.width(key,a),context_minzu.width(key,b)
            quad = [context_minzu.at(key,a,-wa),context_minzu.at(key,b,-wb),
                    context_minzu.at(key,b,wb),context_minzu.at(key,a,wa)]
            faces.extend([[quad[i] for i in tri] for tri in [(0,1,2),(0,2,3)]])
    from terrain_reduction_plan import active_plan_paths
    context_inputs=['data/minzu-plan.json','blender/minzu_avenue.py','blender/forest_canopy.py',
                    'blender/terrain_mesh.py','blender/terrain_reduction_plan.py','blender/reduced_surface.py']
    context_inputs += [str(p.relative_to(ROOT)) for p in active_plan_paths()]
    payload = {'roadFaces': faces, 'geometry': report,
               'inputHashes': {p: hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in context_inputs}}
    output = ROOT/'work/minzu-avenue/road-context.json'
    output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(json.dumps(payload,separators=(',',':'))+'\n')
    print('Prepared Minzu connection context:',report,flush=True)
    sys.exit(0)



if TERRAIN_CONTEXT_ONLY:
    from terrain_context import capture
    capture(globals(),include_ground='--context-ground' in sys.argv)
    raise SystemExit(0)


if '--check-road-interfaces' in sys.argv:
    from check_road_interfaces import capture_interfaces
    capture_interfaces(globals())
    raise SystemExit(0)

if '--capture-road-inputs' in sys.argv:
    from road_inputs import capture_road_inputs
    capture_road_inputs(globals())
    raise SystemExit(0)

print('Building terrain...', flush=True)
ground = build_terrain_mesh(globals())
apply_site_access(globals(),'detail',apply_terrain_reduction(globals(),'detail',ground.finish()))
base = Batch('Plinth', ['base'])
base.box(0,0,-2.6,MAXX-MINX,MAXY-MINY,2.45,'base')
for axis in ['north','south','east','west']:
    count = COLS if axis in ['north','south'] else ROWS
    for i in range(count-1):
        if axis in ['north','south']:
            a=(MINX+(MAXX-MINX)*i/(count-1),MAXY if axis=='north' else MINY)
            b=(MINX+(MAXX-MINX)*(i+1)/(count-1),a[1])
        else:
            a=(MAXX if axis=='east' else MINX,MINY+(MAXY-MINY)*i/(count-1))
            b=(a[0],MINY+(MAXY-MINY)*(i+1)/(count-1))
        base.face([(a[0],a[1],-.15),(b[0],b[1],-.15),(b[0],b[1],height(*b)),(a[0],a[1],height(*a))],'base')
base.finish()
water = Batch('Water',['water'])
for tri in GEO['waterTriangles']:
    x,y=[sum(p[k] for p in tri)/3 for k in [0,1]]
    if custom_water_contains(x,y):continue
    lake_level=reservoir_water_level(x,y)
    if lake_level is None:lake_level=mountain_water_level(x,y)
    water.face([(x,y,.26 if lake_level is None else lake_level) for x,y in tri],'water')
water.finish()
custom_water=Batch('Reservoir_water_custom',['water'])
for triangle in custom_water_triangles():custom_water.face(triangle,'water')
custom_water.finish()

print('Building road network...', flush=True)
viaduct=Viaduct(height, lambda x,y,mobile: terrain_surface(x,y,height,GEO['bounds'],COLS,ROWS,lightweight=mobile))
minzu=MinzuAvenue(viaduct.road_level, lambda x,y,mobile: terrain_surface(x,y,height,GEO['bounds'],COLS,ROWS,lightweight=mobile))
minzu_geometry=minzu.validate()
print('Minzu avenue geometry:',minzu_geometry,flush=True)
river_bridges={identity: RiverBridge(spec,height,minzu.road_level,
    lambda x,y: displayed_ground_bounds(x,y)[1]) for identity,spec in RIVER_BRIDGE_SPECS.items()}
bridge_landings=[]
for river in river_bridges.values():
    for s in [0,river.path.total]:
        px,py,pz=river.at(s)
        bridge_landings.append((px,py,max(0,pz-minzu.road_level(px,py))))

def retained_road_level(x,y):
    return minzu.road_level(x,y)+max((max(0,lift-.20*math.hypot(x-px,y-py))
                                    for px,py,lift in bridge_landings),default=0)

roadbatch=Batch('Roads',['road','highway'])
bridgebatch=Batch('Bridges',['road','bridge'])
elevated=ElevatedRoads(height,lambda x,y,mobile:terrain_surface(x,y,height,GEO['bounds'],COLS,ROWS,lightweight=mobile),bridges=river_bridges.values(),minzu=minzu)
print('Remaining elevated road geometry:',elevated.report,flush=True)
elevated_levels={'detail':elevated.levels}
elevated_floors={'detail':[r['terrainFloor'] for r in elevated.routes]}
rendered_roads=[]
for index, road in enumerate(GEO['roads']):
    if index in MINZU_ROADS or index in RIVER_BRIDGE_ROADS or index in GROUND_ROADS or index in ELEVATED_ROADS: continue
    for points in VIADUCT_PLAN['roadOverrides'].get(str(index), [road['points']]):
        rendered_roads.append({**road, 'points': points})
for road in rendered_roads:
    if road['name'] == '南宁大桥' and road['bridge']:
        # The detailed deck replaces both generic carriageway strips.
        continue
    major = road['class'] in ['trunk','primary','motorway']
    width = .26 if major else (.17 if road['class']=='secondary' else .095)
    target = bridgebatch if road['bridge'] else roadbatch
    points = road['points']
    for a,b in zip(points,points[1:]):
        dx,dy=b[0]-a[0],b[1]-a[1]
        length=math.hypot(dx,dy)
        if length < .001: continue
        # Resample to let roads follow DEM ridges rather than cut through hills.
        steps=max(1,math.ceil(length/.55))
        for k in range(steps):
            x1,y1=a[0]+dx*k/steps,a[1]+dy*k/steps
            x2,y2=a[0]+dx*(k+1)/steps,a[1]+dy*(k+1)/steps
            ox,oy=-dy/length*width/2,dx/length*width/2
            if road['bridge']:
                h1,h2=max(1.1,retained_road_level(x1,y1)),max(1.1,retained_road_level(x2,y2))
            else:
                h1,h2=retained_road_level(x1,y1),retained_road_level(x2,y2)
            target.face([(x1-ox,y1-oy,h1),(x2-ox,y2-oy,h2),(x2+ox,y2+oy,h2),(x1+ox,y1+oy,h1)],'road' if road['bridge'] or not major else 'highway')
road_group=roadbatch.finish(); bridge_group=bridgebatch.finish()
park_paths=Batch('ParkPaths_qingxiu',PARK_PATH_KEYS)
park_path_counts=build_mountain_paths(park_paths,height,GEO['bounds'],COLS,ROWS,False,coarse_terrain_surface)
park_paths.finish().parent=road_group
elevated_batch=Batch('ElevatedRoads',VIADUCT_MATERIALS,spatial=True,weld=True)
build_elevated_structure(elevated_batch,elevated)
elevated_group=elevated_batch.finish();elevated_group.parent=bridge_group;elevated_group['planHash']=ELEVATED_HASH
elevated_details=Batch('ElevatedRoads_Details',VIADUCT_MATERIALS,spatial=True,weld=True)
elevated_counts=build_elevated_details(elevated_details,elevated)
elevated_details_group=elevated_details.finish();elevated_details_group.parent=elevated_group
del elevated_batch,elevated_details
zhuxi_batch=Batch('ZhuxiInterchange',ZHUXI_MATERIALS)
zhuxi_counts=build_zhuxi_details(zhuxi_batch,elevated)
zhuxi_batch.finish().parent=elevated_group
del zhuxi_batch
print('Building terrain-conforming ground streets...',flush=True)
ground_road_batch=Batch('GroundRoads',GROUND_ROAD_MATERIALS,spatial=True,weld=True)
ground_road_counts=build_ground_roads(ground_road_batch,height,GEO['bounds'],COLS,ROWS,bridges=river_bridges.values(),elevated=elevated)
ground_road_group=ground_road_batch.finish()
ground_road_group.parent=road_group
ground_road_group['planHash']=GROUND_ROAD_HASH
ground_road_counts['siteAccess']=append_site_access_roads(globals(),'detail',ground_road_group)
del ground_road_batch
print('Ground road geometry:',ground_road_counts,flush=True)
minzu_batch=Batch('MinzuAvenue',MINZU_MATERIALS,spatial=True)
build_minzu_structure(minzu_batch,minzu)
minzu_group=minzu_batch.finish()
minzu_group.parent=road_group
minzu_group['planHash']=hashlib.sha256((ROOT/'data/minzu-plan.json').read_bytes()).hexdigest()
minzu_details=Batch('MinzuAvenue_Details',MINZU_MATERIALS,spatial=True)
minzu_counts=build_minzu_details(minzu_details,minzu)
minzu_details.finish().parent=minzu_group
del minzu_batch,minzu_details
viaduct_batch=Batch('Landmark_qingxiang-viaduct',VIADUCT_MATERIALS)
build_viaduct_structure(viaduct_batch,viaduct)
viaduct_object=viaduct_batch.finish()
viaduct_object.parent=bridge_group
viaduct_details=Batch('QingxiangViaduct_Details',VIADUCT_MATERIALS)
build_viaduct_details(viaduct_details,viaduct)
viaduct_details.finish().parent=viaduct_object

print('Building continuous railway network...',flush=True)
railway_batch=Batch('Railways',RAILWAY_MATERIALS,spatial=True)
build_railway_structure(railway_batch,railways)
railway_group=railway_batch.finish()
railway_details=Batch('Railway_Details',RAILWAY_MATERIALS,spatial=True)
railway_counts=build_railway_details(railway_details,railways)
railway_details.finish().parent=railway_group
del railway_batch,railway_details
railway_geometry=railways.validate(STATION_SITES)
railway_group['planHash']=hashlib.sha256((ROOT/'data/railways-plan.json').read_bytes()).hexdigest()
print('Railway geometry:',railway_geometry,flush=True)
assert railway_geometry['maxStationDatumError']<1e-7, 'Railway misses station datum'
assert railway_geometry['maxDisplayGrade']<=.120001, 'Railway grade discontinuity'
assert railway_geometry['maxBallastPenetration']<.001, 'Display terrain pierces railway ballast'

print('Building simplified city blocks...', flush=True)
buildings=Batch('Buildings',['building','building2','building3','roof'])
from road_solids import building_limits,building_envelopes as captured_building_envelopes
from urban_blocks import palette_records, build_massing
mapped_buildings_batch=Batch('Buildings_quality',['building','building2','building3','roof'],spatial=True) if any(prepared_building(b) for b in GEO['buildings']) else None
road_building_limits=building_limits()
road_building_envelopes=captured_building_envelopes(GEO) if mapped_buildings_batch is not None else {}
def building_visible(b, railway_hidden=False, legacy=False):
    return city_visibility.building_visible(b, railway_hidden=railway_hidden, legacy=legacy)

legacy_palette={}
if GEO.get('urbanBlocks'):
    hidden_ids={GEO['buildings'][i]['id'] for i in RAILWAY_BUILDINGS}
    for b in palette_records(GEO):
        if building_visible(b,b['id'] in hidden_ids,legacy=True):
            legacy_palette[b['id']]=RNG.choice(['building','building','building','building2','building3'])
block_support=[]
prepared_building_records=[]
for building_index,b in enumerate(GEO['buildings']):
    if not building_visible(b,building_index in RAILWAY_BUILDINGS): continue
    ring=b['rings'][0][:-1]
    x=sum(p[0] for p in ring)/len(ring); y=sum(p[1] for p in ring)/len(ring)
    z=max(.4,height(x,y))+.07
    if inside_nanhu(x-NANHU_X, y-NANHU_Y):
        z=height(x,y)+.018
    hh=b['height']/100*1.55
    key=(b.get('materialKey') or legacy_palette.get(b['id']) or
         ['building','building','building','building2','building3'][int(hashlib.sha256(b['id'].encode()).hexdigest()[:8],16)%5]) if GEO.get('urbanBlocks') else RNG.choice(['building','building','building','building2','building3'])
    if dedicated_dam(b):continue
    if prepared_building(b):
        placement=building_envelope(b,BUILDING_SUPPORT)
        validate_road_envelope(building_index,b,placement,road_building_envelopes)
        if building_index in road_building_limits and road_building_limits[building_index] is None:continue
        mapped_buildings_batch.cell_override=(math.floor((x-MINX)/80),math.floor((y-MINY)/80))
        result=render_prepared_building(mapped_buildings_batch,b,placement,key,road_building_limits.get(building_index))
        if result:
            prepared_building_records.append(result)
            if b.get('massing'):block_support.append(result)
        continue
    if b.get('blockId'):
        if building_index in road_building_limits and road_building_limits[building_index] is None: continue
        result=build_massing(buildings,b,displayed_ground_bounds,key,road_building_limits.get(building_index))
        if result: block_support.append(result)
        continue
    if building_index in road_building_limits:
        limit=road_building_limits[building_index]
        if limit is None:continue
        hh=min(hh,max(0,limit-z))
    for a,c in zip(ring,ring[1:]+ring[:1]):
        buildings.face([(a[0],a[1],z),(c[0],c[1],z),(c[0],c[1],z+hh),(a[0],a[1],z+hh)],key)
    roof_vertices = [Vector((a,b,z+hh)) for a,b in ring]
    for tri in tessellate_polygon([roof_vertices]):
        # Blender 5.2 returns indices; older supported releases return Vectors.
        buildings.face([tuple(roof_vertices[p] if isinstance(p, int) else p) for p in tri],'roof')
buildings_group=buildings.finish()
water_control_records=build_water_controls(globals(),buildings_group)
if mapped_buildings_batch is not None:
    mapped_buildings_batch.finish().parent=buildings_group
if GEO.get('urbanBlocks'):
    legacy_block_ids={b['id'] for b in GEO['buildings'] if b.get('blockId') and not prepared_building(b)}
    assert legacy_block_ids<={r['id'] for r in block_support},'A legacy residential slab was unexpectedly hidden'
    if mapped_buildings_batch is None:
        (ROOT/'work/urban-structure/p1').mkdir(parents=True,exist_ok=True)
        (ROOT/'work/urban-structure/p1/support.json').write_text(json.dumps(block_support,indent=2))
if mapped_buildings_batch is not None:
    output=ROOT/'work/urban-structure/p5/city-buildings.json';output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(json.dumps({'records':prepared_building_records,'blockSupport':block_support,
        'supportPlanSha256':hashlib.sha256(BUILDING_SUPPORT_PATH.read_bytes()).hexdigest()},indent=2)+'\n')

print('Building tree canopy...', flush=True)
trees=Batch('Vegetation',['leaf','leaf2','leaf3','trunk'])
def tree_origins(legacy=False):
    return [(i,x,y,r) for i,(x,y,r) in enumerate(GEO['trees']) if i not in VIADUCT_TREES and i not in RAILWAY_TREES and i not in MINZU_TREES and not inside_landmark(x,y,legacy=legacy)
                 and not any(abs(x-sx)<7 and abs(y-sy)<7 and inside_station(identity,x-sx,y-sy,margin=r+.03)
                             for identity,(sx,sy,_) in STATION_SITES.items())
                 and not inside_tingzi(x-TINGZI_X, y-TINGZI_Y, margin=r+.04)
                 and not inside_changyou(x-CHANGYOU_X, y-CHANGYOU_Y, margin=r*.6+.02)
                 and not inside_nanhu(x-NANHU_X, y-NANHU_Y)]
original_trees=tree_origins()
legacy_tree_colors={i:RNG.choice(['leaf','leaf','leaf2','leaf3']) for i,x,y,r in tree_origins(legacy=True)}
visible_trees = [(i,x,y,r) for i,x,y,r in original_trees if i not in FOREST_REPLACED and i not in GROUND_ROAD_TREES and i not in MOUNTAIN_REMOVED]
for i,x,y,r in original_trees:
    # Keep the original deterministic color sequence when interiors are removed.
    col=legacy_tree_colors.get(i) or ['leaf','leaf','leaf2','leaf3'][int(hashlib.sha256(f'tree/{i}'.encode()).hexdigest()[:8],16)%4]
    if i in FOREST_REPLACED or i in GROUND_ROAD_TREES or i in MOUNTAIN_REMOVED:
        continue
    z=max(.32,terrain_surface(x,y,height,GEO['bounds'],COLS,ROWS))
    scale=canopy_factor(x,y)*landmark_canopy_factor('zhenning',x-CALIBRATION_ORIGINS['zhenning'][0],y-CALIBRATION_ORIGINS['zhenning'][1])
    build_tree(trees,x,y,z,r*scale,col,crown_height=.43*scale,crown_rise=.33*scale,
               trunk_radius=.028*scale,trunk_height=.30*scale)
tree_group=trees.finish()
build_forests(tree_group)
zhuxi_trees=Batch('Vegetation_zhuxi',['leaf','leaf2','leaf3','trunk'])
build_zhuxi_greenery(zhuxi_trees,lambda x,y:terrain_surface(x,y,height,GEO['bounds'],COLS,ROWS))
zhuxi_trees.finish().parent=tree_group
del zhuxi_trees




landmarks=[]
def landmark(id):
    place = PLACE_BY_ID[id]
    x,y,z=pos(place['lon'],place['lat'])
    if id in ['sports-center', 'changyou', *STATIONS]:
        # Open fields and colonnade feet start at their local ground level.
        z = height(x, y)
    if id == 'tingzi': z = terrace_level(x, y, z, height)
    if id == 'zhenning':
        z = zhenning_terrace_level(x, y, lambda u,v: displayed_ground_bounds(u,v)[1],display_scale=CALIBRATION[id]['displayScale'])
    if id in MALL_SITES: z = mall_support_level(id,x,y,displayed_ground_bounds)
    if id in CULTURAL_SPECS: z = cultural_support_level(id,x,y,displayed_ground_bounds,(GEO['bounds'],COLS,ROWS))
    keys=['roof','landmark','accent','bridge','building']
    if id == 'expo': keys += ['expo_membrane','expo_glass','expo_frame','expo_stone']
    if id == 'arts-center': keys += ['arts_white','arts_shell','arts_soffit','arts_glass','arts_frame','arts_stone']
    if id == 'sports-center': keys += SPORTS_MATERIALS
    if id == 'tingzi': keys += TINGZI_MATERIALS
    if id == 'bridge': keys += BRIDGE_MATERIALS
    if id in RIVER_BRIDGE_SPECS: keys += RIVER_BRIDGE_KEYS
    if id == 'changyou': keys += CHANGYOU_MATERIALS
    if id == 'nanhu': keys += NANHU_MATERIALS
    if id == 'zhenning': keys += ZHENNING_MATERIALS
    if id == 'confucius': keys += list(TEMPLE_MATERIALS)
    if id in STATIONS: keys += STATION_MATERIALS
    if id in MALL_SITES: keys += list(MALL_MATS)
    if id in CULTURAL_SPECS: keys += list(CULTURAL_MATS)
    batch=Batch('Landmark_'+id,keys)
    landmarks.append({k:v for k,v in place.items() if k != 'clearExtent'})
    landmarks[-1]['position']=[round(x,3),round(z,3),round(-y,3)]
    return batch,x,y,z

for identity in CULTURAL_SPECS:
    b,x,y,z=landmark(identity)
    build_cultural(b,identity,x,y,z,displayed_ground_bounds)
    b.finish()

b,x,y,z=landmark('cr')
for i in range(8):
    size=.77-i*.055
    b.box(x,y,z+i*.78,size,size,.8,'landmark','roof')
    b.box(x,y,z+i*.78,size+.018,size+.018,.034,'accent')
b.cone(x,y,z+6.3,.23,.08,.6,'landmark',4)
b.finish()

b,x,y,z=landmark('diwang')
z=build_diwang(b,x,y,z,displayed_ground_bounds)
landmarks[-1]['position'][1]=round(z,3)
b.finish()

b,x,y,z=landmark('expo')
build_expo(b,x,y,z)
b.finish()

b,x,y,z=landmark('changyou')
build_changyou(b,x,y,z,height)
b.finish()

b,x,y,z=landmark('nanhu')
nanhu_trees=Batch('Vegetation_nanhu',['nanhu_trunk','nanhu_palm','nanhu_leaf','nanhu_leaf_light','nanhu_leaf_dark'])
landmarks[-1]['position'][1]=round(build_nanhu(b,x,y,height,nanhu_trees),3)
nanhu_trees.finish().parent=tree_group
b.finish()

b,x,y,z=landmark('bridge')
bridge_center=build_bridge(b,GEO['roads'],height)
# Keep the geographic catalog point, and anchor the label at deck height.
landmarks[-1]['position'][1]=round(bridge_center[2],3)
b.finish().parent=bridge_group

for identity,river in river_bridges.items():
    b,x,y,z=landmark(identity)
    build_river_bridge(b,river)
    obj=b.finish()
    obj.parent=bridge_group
    obj['bridgeType']=river.kind
    obj['sourceRoadIndices']=river.spec['roadIndices']
    obj['planHash']=hashlib.sha256((ROOT/'data/bridges-plan.json').read_bytes()).hexdigest()
    center=river.at((river.start+river.end)/2)
    landmarks[-1]['position']=[round(center[0],3),round(center[2],3),round(-center[1],3)]
    details=Batch('RiverBridge_Details_'+identity,RIVER_BRIDGE_KEYS)
    build_river_details(details,river)
    details.finish().parent=obj

for place in CATALOG:
    if not place['modelled']:
        x,y,z=pos(place['lon'],place['lat'])
        landmarks.append({**place,'position':[round(x,3),round(max(.3,z),3),round(-y,3)]})

# Additional cultural, campus, riverside and transport landmarks.
b,x,y,z=landmark('zhenning')
def fort_ground_bounds(u,v):
    # First treads meet the displayed triangles. Including the unrendered
    # bilinear DEM here raised the outer landings above both visible surfaces.
    levels=[terrain_surface(u,v,height,GEO['bounds'],COLS,ROWS,profile) for profile in [False,True]]
    return min(levels),max(levels)
build_zhenning(b,x,y,z,ground_bounds=fort_ground_bounds,
                display_scale=CALIBRATION['zhenning']['displayScale'],height_scale=CALIBRATION['zhenning']['heightScale'])
b.finish()
calibrated_support={}
def record_calibrated_support(identity,result):
    calibrated_support[identity]=result
    next(p for p in landmarks if p['id']==identity)['position'][1]=round(result['anchorLevel'],3)
build_extra_landmarks(landmark,height,displayed_ground_bounds,(GEO['bounds'],COLS,ROWS),record_calibrated_support)
for identity in MALL_SITES:
    b,x,y,z=landmark(identity)
    build_mall(b,identity,x,y,z,displayed_ground_bounds)
    b.finish()
place=PLACE_BY_ID['qingxiang-viaduct']
x,y,_=pos(place['lon'],place['lat'])
distance=viaduct.main.nearest(x,y)[1]
landmarks.append({**place,'position':[round(x,3),round(viaduct.render_level('main',distance),3),round(-y,3)]})
landmarks.sort(key=lambda place: next(i for i,p in enumerate(CATALOG) if p['id']==place['id']))

(ROOT/'public/data/landmarks.json').write_text(json.dumps(landmarks,ensure_ascii=False,indent=2))
# Minimal overview data avoids downloading the geometry database at runtime.
summary={k:GEO[k] for k in ['bbox','center','bounds','metersPerUnit','osmTimestamp']}
summary['waterControls']=[{'id':r['id'],'buildingId':r['buildingId'],'node':r['node'],
                          'parts':len(r['geometry']['parts']),'estimatedGateBays':r['geometry']['openings']} for r in water_control_records]
summary['stats']={**GEO['stats'],'trees':len(visible_trees)}
summary['riverBridges']={'count':len(river_bridges)+1,'added':len(river_bridges),
    'replacedRoadStrips':len(RIVER_BRIDGE_ROADS),'osmTimestamp':RIVER_BRIDGE_PLAN['osmTimestamp'],
    'planHash':hashlib.sha256((ROOT/'data/bridges-plan.json').read_bytes()).hexdigest()}
summary['groundRoads']={**GROUND_ROAD_PLAN['stats'],'detail':ground_road_counts,
    'removedVisibleTrees':sum(i not in FOREST_REPLACED and i in GROUND_ROAD_TREES for i,x,y,r in original_trees),
    'planHash':GROUND_ROAD_HASH}
summary['elevatedRoads']={**elevated.report,'detail':elevated_counts}
summary['minzuAvenue']={**MINZU_PLAN['stats'],'geometry':minzu_geometry,'detailFittings':minzu_counts,
    'osmTimestamp':MINZU_PLAN['osmTimestamp'],'planHash':hashlib.sha256((ROOT/'data/minzu-plan.json').read_bytes()).hexdigest()}
summary['railways']={**RAILWAY_PLAN['stats'],'osmTimestamp':RAILWAY_PLAN['osmTimestamp'],
    'detailFittings':railway_counts,'geometry':railway_geometry,
    'terrainCuts':railways.cuts,
    'planHash':hashlib.sha256((ROOT/'data/railways-plan.json').read_bytes()).hexdigest()}
summary['viaduct']={'id':VIADUCT_PLAN['id'],'mainLengthMeters':VIADUCT_PLAN['main']['lengthMeters'],
    'scope':VIADUCT_PLAN['scope'],'mainWays':len(VIADUCT_PLAN['main']['osmIds']),
    'ramps':VIADUCT_PLAN['mainConnections'],'linkWays':len({r['osmId'] for r in VIADUCT_PLAN['ramps']}),
    'linkSections':len(VIADUCT_PLAN['ramps']),'piers':len(viaduct.piers),'osmTimestamp':VIADUCT_PLAN['osmTimestamp']}
summary['forestCanopy']={'areaKm2':FOREST_PLAN['areaKm2'],'stage':FOREST_PLAN['stage'],
    'source':'OSM natural=wood / landuse=forest','sourceCount':len(FOREST_PLAN['sources']),
    'regions':[{'id':r['id'],'areaKm2':r['areaKm2']} for r in FOREST_REGIONS],
    'replacedTrees':sum(i in FOREST_REPLACED for i,x,y,r in original_trees)}
summary['qingxiuTerrain']={**MOUNTAIN_PLAN['statistics'],'detailPaths':park_path_counts,'planHash':hashlib.sha256((ROOT/'data/qingxiu-terrain-plan.json').read_bytes()).hexdigest()}
summary['landmarkCalibration']={'sites':list(CALIBRATION),'support':calibrated_support,
    'vegetation':LANDMARK_VEGETATION,
    'sourceHash':hashlib.sha256((ROOT/'data/landmark-calibration-source.json').read_bytes()).hexdigest(),
    'note':'Source-sized illustrative landmarks; secondary dimensions and terraced temple layout are estimates.'}
summary['previousBbox']=json.loads((ROOT/'data/region.json').read_text())['previousBbox']
summary.update({'water':GEO['water'],'minElevation':DEM['minElevation'],'maxElevation':DEM['maxElevation'],'terrainExaggeration':SCALE_Z,'buildingExaggeration':1.55})
# Compound templates already store their displayed part heights in metres.
summary['buildingScaleOverrides']=[{'blockId':b['id'],'scale':b['template'].get('displayHeightScale',1.0),
                                   'layoutSource':b['layoutSource'],'buildings':len(b['buildingIds'])}
                                  for b in GEO.get('urbanBlocks',[])]
(ROOT/'public/data/overview.json').write_text(json.dumps(summary,ensure_ascii=False,separators=(',',':')))

print('Saving Blender source and glTF...', flush=True)
bpy.ops.object.camera_add(location=(220,-290,280))
camera=bpy.context.object
camera.name='OverviewCamera'
direction=Vector((0,0,0))-camera.location
camera.rotation_euler=direction.to_track_quat('-Z','Y').to_euler()
camera.data.type='ORTHO';camera.data.ortho_scale=max(MAXX-MINX,MAXY-MINY)*1.42
bpy.context.scene.camera=camera
bpy.ops.object.light_add(type='AREA',location=(-60,-30,160))
bpy.context.object.data.energy=80000
bpy.context.object.data.shape='DISK';bpy.context.object.data.size=110
bpy.context.scene.world.use_nodes=True
world_background=bpy.context.scene.world.node_tree.nodes.get('Background')
world_background.inputs['Color'].default_value=(.68,.76,.70,1)
world_background.inputs['Strength'].default_value=.65
bpy.context.scene.view_settings.view_transform='AgX'
bpy.context.scene.render.engine='CYCLES'
bpy.context.scene.cycles.samples=24
bpy.context.scene.render.resolution_x=1600
bpy.context.scene.render.resolution_y=1100
bpy.context.scene.render.resolution_percentage=100
bpy.ops.wm.save_as_mainfile(filepath=str(ROOT/'blender/nanning-city.blend'))
# 18-bit positions preserve the narrow rail heads in 8 km spatial batches.
export_city(ROOT/'public/models/nanning-city.glb')
print('City complete:',len(GEO['buildings']),'buildings,',len(visible_trees),'trees,',len(landmarks),'landmarks.',flush=True)

# Keep the editable .blend at full detail; export a separate lightweight model.
# Structural roads and landmarks remain complete; viaduct fittings are reduced.
for child in list(elevated_group.children_recursive):
    mesh=child.data;bpy.data.objects.remove(child,do_unlink=True)
    if mesh is not None:bpy.data.meshes.remove(mesh)
bpy.data.objects.remove(elevated_group,do_unlink=True)
elevated=ElevatedRoads(height,lambda x,y,mobile:terrain_surface(x,y,height,GEO['bounds'],COLS,ROWS,lightweight=mobile),bridges=river_bridges.values(),lightweight=True,minzu=minzu)
elevated_levels['smooth']=elevated.levels
elevated_floors['smooth']=[r['terrainFloor'] for r in elevated.routes]
summary['elevatedRoads']['smoothGeometry']=elevated.report
elevated_batch=Batch('ElevatedRoads',VIADUCT_MATERIALS,spatial=True,weld=True)
build_elevated_structure(elevated_batch,elevated)
elevated_group=elevated_batch.finish();elevated_group.parent=bridge_group;elevated_group['planHash']=ELEVATED_HASH
del elevated_batch
elevated_details=Batch('ElevatedRoads_Details',VIADUCT_MATERIALS,spatial=True,weld=True)
summary['elevatedRoads']['smooth']=build_elevated_details(elevated_details,elevated,lightweight=True)
elevated_details.finish().parent=elevated_group
del elevated_details
zhuxi_batch=Batch('ZhuxiInterchange',ZHUXI_MATERIALS)
build_zhuxi_details(zhuxi_batch,elevated)
zhuxi_batch.finish().parent=elevated_group
del zhuxi_batch
for identity,river in river_bridges.items():
    detail_object=bpy.data.objects['RiverBridge_Details_'+identity]
    detail_mesh=detail_object.data
    bpy.data.objects.remove(detail_object,do_unlink=True)
    bpy.data.meshes.remove(detail_mesh)
    details=Batch('RiverBridge_Details_'+identity,RIVER_BRIDGE_KEYS)
    build_river_details(details,river,lightweight=True)
    details.finish().parent=bpy.data.objects['Landmark_'+identity]

detail_object=bpy.data.objects['QingxiangViaduct_Details']
detail_mesh=detail_object.data
bpy.data.objects.remove(detail_object,do_unlink=True)
bpy.data.meshes.remove(detail_mesh)
mobile_viaduct_details=Batch('QingxiangViaduct_Details',VIADUCT_MATERIALS)
build_viaduct_details(mobile_viaduct_details,viaduct,lightweight=True)
mobile_viaduct_details.finish().parent=viaduct_object
minzu_detail_object=bpy.data.objects['MinzuAvenue_Details']
for child in list(minzu_detail_object.children_recursive):
    mesh=child.data
    bpy.data.objects.remove(child,do_unlink=True)
    bpy.data.meshes.remove(mesh)
bpy.data.objects.remove(minzu_detail_object,do_unlink=True)
for child in list(minzu_group.children):
    mesh=child.data
    bpy.data.objects.remove(child,do_unlink=True)
    if mesh is not None:bpy.data.meshes.remove(mesh)
bpy.data.objects.remove(minzu_group,do_unlink=True)
mobile_minzu_structure=Batch('MinzuAvenue',MINZU_MATERIALS,spatial=True)
build_minzu_structure(mobile_minzu_structure,minzu,lightweight=True)
minzu_group=mobile_minzu_structure.finish();minzu_group.parent=road_group
minzu_group['planHash']=hashlib.sha256((ROOT/'data/minzu-plan.json').read_bytes()).hexdigest()
del mobile_minzu_structure
mobile_minzu_details=Batch('MinzuAvenue_Details',MINZU_MATERIALS,spatial=True)
summary['minzuAvenue']['smoothFittings']=build_minzu_details(mobile_minzu_details,minzu,lightweight=True)
mobile_minzu_details.finish().parent=minzu_group
del mobile_minzu_details
railway_detail_object=bpy.data.objects['Railway_Details']
for child in list(railway_detail_object.children_recursive):
    mesh=child.data
    bpy.data.objects.remove(child,do_unlink=True)
    bpy.data.meshes.remove(mesh)
bpy.data.objects.remove(railway_detail_object,do_unlink=True)
mobile_railway_details=Batch('Railway_Details',RAILWAY_MATERIALS,spatial=True)
summary['railways']['smoothFittings']=build_railway_details(mobile_railway_details,railways,lightweight=True)
mobile_railway_details.finish().parent=railway_group
del mobile_railway_details
for name in ['Terrain','Vegetation']:
    obj=bpy.data.objects.get(name)
    for child in list(obj.children_recursive): bpy.data.objects.remove(child,do_unlink=True)
    bpy.data.objects.remove(obj,do_unlink=True)
mobile_ground=build_terrain_mesh(globals(),lightweight=True)
old_paths=bpy.data.objects['ParkPaths_qingxiu'];old_path_mesh=old_paths.data
bpy.data.objects.remove(old_paths,do_unlink=True);bpy.data.meshes.remove(old_path_mesh)
mobile_paths=Batch('ParkPaths_qingxiu',PARK_PATH_KEYS)
summary['qingxiuTerrain']['smoothPaths']=build_mountain_paths(mobile_paths,height,GEO['bounds'],COLS,ROWS,True,coarse_terrain_surface)
mobile_paths.finish().parent=road_group
apply_site_access(globals(),'smooth',apply_terrain_reduction(globals(),'smooth',mobile_ground.finish()))
mobile_trees=Batch('Vegetation',['leaf','leaf2','leaf3','trunk'])
mobile_tree_count=0
# Subsample the original positions before removing covered forest interiors.
legacy_tree_ids={i for i,x,y,r in tree_origins(legacy=True)}
legacy_mobile_colors={i:['leaf','leaf2','leaf3'][order%3] for order,(i,x,y,r) in enumerate(tree_origins(legacy=True)[::4])}
for i,x,y,r in original_trees:
    if i not in legacy_mobile_colors and (i in legacy_tree_ids or i%4):continue
    if i in FOREST_REPLACED or i in GROUND_ROAD_TREES or i in MOUNTAIN_REMOVED:
        continue
    mobile_tree_count+=1
    col=legacy_mobile_colors.get(i) or ['leaf','leaf2','leaf3'][i%3]
    z=max(.32,terrain_surface(x,y,height,GEO['bounds'],COLS,ROWS,lightweight=True))
    scale=canopy_factor(x,y)*landmark_canopy_factor('zhenning',x-CALIBRATION_ORIGINS['zhenning'][0],y-CALIBRATION_ORIGINS['zhenning'][1])
    build_tree(mobile_trees,x,y,z,r*scale,col,lightweight=True,crown_height=.43*scale,crown_rise=.33*scale,
               trunk_radius=.028*scale,trunk_height=.30*scale)
mobile_tree_group=mobile_trees.finish()
build_forests(mobile_tree_group,lightweight=True)
zhuxi_trees=Batch('Vegetation_zhuxi',['leaf','leaf2','leaf3','trunk'])
build_zhuxi_greenery(zhuxi_trees,lambda x,y:terrain_surface(x,y,height,GEO['bounds'],COLS,ROWS,lightweight=True),lightweight=True)
zhuxi_trees.finish().parent=mobile_tree_group
del zhuxi_trees
nanhu_trees.finish().parent=mobile_tree_group
for child in list(ground_road_group.children_recursive):
    mesh=child.data
    bpy.data.objects.remove(child,do_unlink=True)
    bpy.data.meshes.remove(mesh)
bpy.data.objects.remove(ground_road_group,do_unlink=True)
mobile_ground_roads=Batch('GroundRoads',GROUND_ROAD_MATERIALS,spatial=True,weld=True)
summary['groundRoads']['smooth']=build_ground_roads(mobile_ground_roads,height,GEO['bounds'],COLS,ROWS,lightweight=True,bridges=river_bridges.values(),elevated=elevated)
mobile_ground_road_group=mobile_ground_roads.finish()
mobile_ground_road_group.parent=road_group
mobile_ground_road_group['planHash']=summary['groundRoads']['planHash']
summary['groundRoads']['smooth']['siteAccess']=append_site_access_roads(globals(),'smooth',mobile_ground_road_group)
del mobile_ground_roads
export_city(ROOT/'public/models/nanning-city-mobile.glb')
(ROOT/'data/elevated-roads-heights.json.gz').write_bytes(gzip.compress(json.dumps({'planHash':ELEVATED_HASH,'profiles':elevated_levels,'terrainFloors':elevated_floors},separators=(',',':')).encode(),mtime=0))
summary['mobileTrees']=mobile_tree_count
summary['models']={}
for key,filename in [('detail','nanning-city.glb'),('smooth','nanning-city-mobile.glb')]:
    summary['models'][key]={'file':filename,'bytes':(ROOT/'public/models'/filename).stat().st_size}
(ROOT/'public/data/overview.json').write_text(json.dumps(summary,ensure_ascii=False,separators=(',',':')))
print('Desktop and mobile model variants complete.',flush=True)
