"""Shared conversion from attributed display elevations into atlas scene units."""
def scene_height(meters,terrain):
    return max(-.08,terrain.get('verticalOffset',0)+(meters-terrain.get('verticalDatumMeters',55))/100*terrain.get('verticalExaggeration',3))
