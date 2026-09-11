# Attribution

## OpenStreetMap

© OpenStreetMap contributors. Geographic data is available under the [Open Data Commons Open Database License (ODbL) 1.0](https://opendatacommons.org/licenses/odbl/1-0/).

The derived geographic database is distributed in `public/data/geography.json`. The Blender scene and GLB are produced works derived in part from that database. Retain this attribution when redistributing the models, scene, renders, or geographic data.

See [OpenStreetMap copyright](https://www.openstreetmap.org/copyright).

## Elevation

Copernicus DEM GLO-30, 2021 release, accessed 2026-09-11 through [AWS / Sinergise](https://registry.opendata.aws/copernicus-dem/). Source DSM resolution is 1 arc-second; this project resamples to approximately 60 m and conditions a separate illustrative display surface.

produced using Copernicus WorldDEM-30 © DLR e.V. 2010-2014 and © Airbus Defence and Space GmbH 2014-2018 provided under COPERNICUS by the European Union and ESA; all rights reserved.

The organisations in charge of the Copernicus programme by law or by delegation do not incur any liability for any use of the Copernicus WorldDEM-30.

Source: https://registry.opendata.aws/copernicus-dem/
Licence: https://copernicus-dem-30m.s3.amazonaws.com/Copernicus_DSM_COG_10_N22_00_E108_00_DEM/INFO/eula_F.pdf

Resampled and conditioned for an illustrative city model. Downstream redistribution must retain the source and liability notices and the obligations in Article 6 of the source licence.

The displayed terrain is not a surveyed bare-earth model. The source data providers do not endorse these modifications. Historical versions used Mapzen / AWS Terrain Tiles and SRTM; the current terrain no longer uses those tiles.

## Software

Three.js — MIT. Blender — GPL. Shapely — BSD. Rasterio — BSD. SciPy — BSD. Pillow — HPND. Mapbox Earcut — ISC. Google Draco — Apache 2.0; decoder license included in `public/draco/LICENSE.txt`. Other JavaScript dependencies retain their package licenses.

The root MIT license applies to this project's authored code, not to third-party geographic datasets or third-party software.
