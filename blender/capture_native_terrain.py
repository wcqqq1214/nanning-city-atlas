"""Run only the production terrain statements, without exporting city assets.

AST boundaries deliberately fail if the builder is reorganized. The captured
mesh uses the production Batch and its float32 storage, before Draco encoding.
"""
import ast
from pathlib import Path
import sys


def capture(profile):
    if profile not in ('detail', 'smooth'):
        raise ValueError(profile)
    source = Path(__file__).with_name('build_city.py')
    tree = ast.parse(source.read_text())
    stop = next(i for i, n in enumerate(tree.body) if isinstance(n, ast.If)
                and isinstance(n.test, ast.Name) and n.test.id == 'TERRAIN_CONTEXT_ONLY')
    statements=ast.parse(f'build_terrain_mesh(globals(),lightweight={profile=="smooth"}).finish()').body
    selected = ast.Module(body=tree.body[:stop] + statements, type_ignores=[])
    # The context flag bypasses only resolved-road fingerprints; all geographic,
    # terrain, forest and native road source checks in the prefix still run.
    argv = sys.argv[:]
    try:
        skip={i for j,value in enumerate(sys.argv) if value in ['--terrain-reduction-plan','--site-access-plan','--building-support-plan'] for i in [j,j+1]}
        sys.argv[:]=[v for i,v in enumerate(sys.argv) if i not in skip]
        sys.argv.append('--terrain-context')
        env = {'__file__': str(source), '__name__': '__terrain_capture__'}
        from terrain_reduction_plan import suspended
        from site_access_plan import suspended as access_suspended
        with suspended(),access_suspended():exec(compile(ast.fix_missing_locations(selected), str(source), 'exec'), env)
    finally:
        sys.argv[:] = argv
    return env
