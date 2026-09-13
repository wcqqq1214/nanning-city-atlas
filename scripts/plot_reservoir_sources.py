"""Plot source reservoir/dam relationships and DSM profiles, not final scene renders."""
import argparse
import json
import math
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
import rasterio
from rasterio.windows import from_bounds
from shapely.geometry import shape
from audit_reservoir_sources import digest


def boundaries(ax, geometry, **kwargs):
    if geometry.geom_type == 'Polygon':
        for ring in [geometry.exterior, *geometry.interiors]:
            p = np.asarray(ring.coords)*100
            ax.plot(p[:, 0], p[:, 1], **kwargs)
    else:
        for part in geometry.geoms:
            boundaries(ax, part, **kwargs)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--inventory', required=True, type=Path)
    parser.add_argument('--output-directory', required=True, type=Path)
    args = parser.parse_args()
    inventory = json.loads(args.inventory.read_text())
    for value in inventory['inputs'].values():
        if digest(Path(value['path'])) != value['sha256']:
            raise ValueError('Inventory input changed: '+value['path'])
    geo = json.loads(Path(inventory['inputs']['geography']['path']).read_text())
    cx, cy = geo['center'];kx = 1113.2*math.cos(math.radians(cy))
    water_lookup = {w['sourceRef']: w for w in inventory['waters']}
    fig, axes = plt.subplots(4, 3, figsize=(15, 18), constrained_layout=True)
    profiles, profile_axes = plt.subplots(4, 3, figsize=(15, 13), constrained_layout=True)
    with rasterio.open(inventory['inputs']['raster']['path']) as raster:
        for ax, pax, record in zip(axes.flat, profile_axes.flat, inventory['records']):
            dam = shape(record['sourceGeometry']);center = dam.centroid
            radius = max(1.6, max(dam.bounds[2]-dam.bounds[0], dam.bounds[3]-dam.bounds[1])*1.4)
            w, s, e, n = center.x-radius, center.y-radius, center.x+radius, center.y+radius
            window = from_bounds(cx+w/kx, cy+s/1113.2, cx+e/kx, cy+n/1113.2, raster.transform)
            window = window.round_offsets().round_lengths()
            data = raster.read(1, window=window, masked=True)
            left, bottom, right, top = rasterio.windows.bounds(window, raster.transform)
            ax.imshow(data, extent=[(left-cx)*kx*100, (right-cx)*kx*100,
                                    (bottom-cy)*111320, (top-cy)*111320],
                      origin='upper', cmap='terrain', interpolation='nearest')
            for nearby in record['nearbyWaters']:
                water = water_lookup[nearby['sourceRef']]
                boundaries(ax, shape(water['sourceGeometry']), color='#0077bb', linewidth=1.4)
                for match in water['displayMatches']:
                    rings = geo['water'][match['index']]
                    from shapely.geometry import Polygon
                    boundaries(ax, Polygon(rings[0], rings[1:]), color='#ffffff', linewidth=.9, linestyle='--')
            boundaries(ax, dam, color='#e64b00', linewidth=2.5)
            points = np.asarray(record['rawDsmLongAxis']['pointsSceneXY'])*100
            ax.plot(points[:, 0], points[:, 1], color='#202020', linewidth=1)
            ax.set_xlim(w*100, e*100);ax.set_ylim(s*100, n*100);ax.set_aspect('equal')
            ax.set_title(record['sourceRef']+' | '+('prepared' if record['usesPreparedBuildingPath'] else 'legacy'), fontsize=10)
            ax.tick_params(labelsize=7);ax.set_xlabel('East (m)', fontsize=8);ax.set_ylabel('North (m)', fontsize=8)
            distance = np.linalg.norm(points-points[0], axis=1)
            pax.plot(distance, record['rawDsmLongAxis']['sourceMeters'], color='#252525', label='DSM long-axis samples')
            for nearby in record['nearbyWaters']:
                water = water_lookup[nearby['sourceRef']]
                candidate = water['displayLevelCandidate']
                if candidate['levelMeters'] is not None:
                    pax.axhline(candidate['levelMeters'], color='#0077bb', linestyle='--', label='Water display candidate')
            pax.set_title(record['sourceRef'], fontsize=10);pax.set_xlabel('Profile distance (m)', fontsize=8)
            pax.set_ylabel('DSM elevation (m EGM2008)', fontsize=8);pax.grid(alpha=.2)
        axes.flat[-1].axis('off');profile_axes.flat[-1].axis('off')
    fig.suptitle('All 11 mapped dams: source DSM pixels and plan geometry\nOrange: source dam | Blue: source water | White dashed: existing display shoreline', fontsize=14)
    profiles.suptitle('DSM profiles are NOT surveyed dam crests\nDashed water levels are unapplied display candidates, not engineering operating levels', fontsize=14)
    args.output_directory.mkdir(parents=True, exist_ok=True)
    fig.savefig(args.output_directory/'source-map.png', dpi=140)
    profiles.savefig(args.output_directory/'source-profiles.png', dpi=140)
    plt.close('all')
    result = {'inventorySha256': digest(args.inventory), 'plotterSha256': digest(Path(__file__)),
              'status': 'source plots; not Blender/runtime verification',
              'images': {p.name: digest(p) for p in args.output_directory.glob('source-*.png')}}
    (args.output_directory/'plots.json').write_text(json.dumps(result, indent=2)+'\n')


if __name__ == '__main__':
    main()
