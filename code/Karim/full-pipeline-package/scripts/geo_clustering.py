"""
Shared geo-math helpers used by more than one script: single-linkage
distance clustering (grouping nearby points into one cluster) and the
EPSG:2263 <-> WGS84 reprojection both build_capture_coverage_hull.py and
fetch_cyclomedia_panoramas.py need. Extracted from
build_capture_coverage_hull.py (2026-08-14) once a second caller
(fetch_cyclomedia_panoramas.py's intersection-clustering, at a much
tighter threshold) needed the same logic.
"""
from pyproj import Transformer

_TO_LAT_LON = Transformer.from_crs("EPSG:2263", "EPSG:4326", always_xy=True)


def cluster_points_by_distance(xy_points, threshold_ft):
    """xy_points: list of (x, y) coordinates in a linear unit (e.g. EPSG:2263
    feet). Single-linkage clustering via union-find: two points merge into
    the same cluster if within threshold_ft of each other, and clusters
    chain transitively (a point within range of *any* member of a cluster
    joins it, not just the cluster's centroid). Returns a list of clusters,
    each a list of the original (x, y) points, in first-seen order; cluster
    order is otherwise unspecified. O(n^2) -- fine for the low hundreds of
    points this project's capture manifests/boards currently produce.

    threshold_ft has no default -- the right value is scale-dependent
    (neighborhood-scale grouping vs. single-intersection grouping use very
    different distances), so every caller states its own explicitly rather
    than risking a silently-wrong shared default."""
    n = len(xy_points)
    parent = list(range(n))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    def union(i, j):
        ri, rj = find(i), find(j)
        if ri != rj:
            parent[ri] = rj

    for i in range(n):
        xi, yi = xy_points[i]
        for j in range(i + 1, n):
            xj, yj = xy_points[j]
            if ((xi - xj) ** 2 + (yi - yj) ** 2) ** 0.5 <= threshold_ft:
                union(i, j)

    groups = {}
    for i in range(n):
        groups.setdefault(find(i), []).append(xy_points[i])
    return list(groups.values())


def reproject_2263_to_lat_lon(x, y):
    """EPSG:2263 (x, y) in US feet -> WGS84 (lat, lon). Inverse of
    physical_report_lib.reproject_lat_lon_to_2263."""
    lon, lat = _TO_LAT_LON.transform(x, y)
    return lat, lon
