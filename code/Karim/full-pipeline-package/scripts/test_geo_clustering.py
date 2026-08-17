import geo_clustering as gc


def test_cluster_points_by_distance_separates_far_apart_groups():
    points = [(0, 0), (1, 1), (2, 0), (10_000, 10_000), (10_001, 10_001)]
    clusters = gc.cluster_points_by_distance(points, threshold_ft=100)
    sizes = sorted(len(c) for c in clusters)
    assert sizes == [2, 3]


def test_cluster_points_by_distance_chains_transitively():
    # A and B are close, B and C are close, but A and C are not directly
    # within threshold -- single-linkage should still merge all three via B.
    points = [(0, 0), (90, 0), (180, 0)]
    clusters = gc.cluster_points_by_distance(points, threshold_ft=100)
    assert len(clusters) == 1
    assert len(clusters[0]) == 3


def test_reproject_2263_to_lat_lon_matches_known_corner():
    # Real corner from a fetched board (cb211_000, data/cyclomedia_panoramas/
    # cb211/signs_data.json) -- both its x_2263/y_2263 and latitude/longitude
    # are already-verified real values from this project's own forward
    # transform, so this checks the inverse lands within a tight tolerance.
    lat, lon = gc.reproject_2263_to_lat_lon(1020145.0, 245201.0)
    assert abs(lat - 40.83962235520697) < 0.0001
    assert abs(lon - (-73.87027467089928)) < 0.0001
