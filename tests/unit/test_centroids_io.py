"""Centroid files are loaded without pickle: they are mounted from a ConfigMap, so they are untrusted input."""

import pickle

import numpy as np
import pytest

from guardrails.layer2_classifier import load_centroids, save_centroids


class TestRoundTrip:
    def test_centroids_survive_a_save_and_load(self, tmp_path):
        original = {"GST": np.array([0.1, 0.2, 0.3]), "PAYROLL": np.array([0.4, 0.5, 0.6])}
        path = tmp_path / "centroids.npz"
        save_centroids(original, path)
        loaded = load_centroids(path)
        assert set(loaded) == {"GST", "PAYROLL"}
        for name in original:
            np.testing.assert_allclose(loaded[name], original[name])

    def test_loaded_values_are_plain_arrays(self, tmp_path):
        path = tmp_path / "c.npz"
        save_centroids({"GST": np.ones(4)}, path)
        assert isinstance(load_centroids(path)["GST"], np.ndarray)

    def test_the_archive_is_readable_with_pickle_disabled(self, tmp_path):
        path = tmp_path / "c.npz"
        save_centroids({"GST": np.ones(4)}, path)
        with np.load(str(path), allow_pickle=False) as data:
            assert data.files == ["GST"]


class TestUntrustedFiles:
    def test_the_old_pickled_npy_format_is_refused_with_a_clear_message(self, tmp_path):
        path = tmp_path / "centroids.npy"
        np.save(str(path), {"GST": np.ones(3)}, allow_pickle=True)
        with pytest.raises(ValueError, match="pickled .npy.*build_centroids"):
            load_centroids(path)

    def test_an_archive_containing_pickled_objects_is_not_unpickled(self, tmp_path):
        """If a malicious file renames itself .npz, loading must still not execute its payload."""
        ran = tmp_path / "pwned.txt"

        class Evil:
            def __reduce__(self):
                return (ran.write_text, ("code ran",))

        path = tmp_path / "centroids.npz"
        np.savez(str(path), GST=np.array([Evil()], dtype=object))
        with pytest.raises(ValueError, match="allow_pickle"):
            load_centroids(path)["GST"]
        assert not ran.exists()

    def test_a_raw_pickle_file_is_not_a_valid_archive(self, tmp_path):
        path = tmp_path / "centroids.npz"
        path.write_bytes(pickle.dumps({"GST": np.ones(3)}))
        with pytest.raises(Exception):
            load_centroids(path)
