"""Tests for water mist targeting.

# IMP-009 — Water Mist Zone Targeting
"""
import pytest

from fire_suppression.actuation.targeting import NozzlePosition, WaterMistTargeter


class TestWaterMistTargeter:
    """# IMP-009 — Water Mist Zone Targeting"""

    def test_add_nozzle(self) -> None:
        targeter = WaterMistTargeter()
        targeter.add_nozzle(NozzlePosition("north", row=2, col=2, relay_index=0))
        assert len(targeter.get_nozzle_positions()) == 1

    def test_target_single_nozzle(self) -> None:
        targeter = WaterMistTargeter()
        targeter.add_nozzle(NozzlePosition("center", row=4, col=4, relay_index=0, spray_range_px=10))
        hotspots = [{"centroid_row": 4, "centroid_col": 4, "size": 5}]
        result = targeter.target(hotspots)
        assert 0 in result.target_nozzles
        assert result.distance_to_closest == pytest.approx(0.0, abs=0.01)

    def test_target_closest_of_multiple(self) -> None:
        targeter = WaterMistTargeter()
        # North is far from the hotspot so it won't be included
        targeter.add_nozzle(NozzlePosition("north", row=1, col=1, relay_index=0, spray_range_px=3))
        targeter.add_nozzle(NozzlePosition("south", row=6, col=6, relay_index=1, spray_range_px=50))
        hotspots = [{"centroid_row": 6, "centroid_col": 6, "size": 5}]
        result = targeter.target(hotspots)
        assert 1 in result.target_nozzles
        assert 0 not in result.target_nozzles

    def test_target_no_hotspots_activates_all(self) -> None:
        targeter = WaterMistTargeter()
        targeter.add_nozzle(NozzlePosition("a", row=2, col=2, relay_index=0))
        result = targeter.target([])
        assert result.target_nozzles == [0]

    def test_target_out_of_range_fallback(self) -> None:
        targeter = WaterMistTargeter()
        targeter.add_nozzle(NozzlePosition("near", row=2, col=2, relay_index=0, spray_range_px=1))
        hotspots = [{"centroid_row": 7, "centroid_col": 7, "size": 5}]
        result = targeter.target(hotspots)
        # Fallback: activate all nozzles
        assert 0 in result.target_nozzles

    def test_target_centroid_returned(self) -> None:
        targeter = WaterMistTargeter()
        targeter.add_nozzle(NozzlePosition("center", row=4, col=4, relay_index=0, spray_range_px=10))
        hotspots = [{"centroid_row": 4, "centroid_col": 4, "size": 5}]
        result = targeter.target(hotspots)
        assert result.target_centroid == (4, 4)
