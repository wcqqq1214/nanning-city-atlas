import contextlib
import io
import unittest

from check_city_streaming import validate


class StreamingAssetsTests(unittest.TestCase):
    def test_both_published_profiles_partition_validated_models_exactly(self):
        with contextlib.redirect_stdout(io.StringIO()):
            validate()
