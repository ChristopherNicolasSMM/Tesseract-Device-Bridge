import pytest

from recipe_engine.state import RecipeState


def test_default_state_is_idle():
    state = RecipeState()
    assert state.status == "idle"
    assert state.recipe_name is None


def test_fresh_state_starts_ramping_at_step_zero():
    state = RecipeState.fresh("Pilsen")
    assert state.status == "ramping"
    assert state.step_index == 0
    assert state.recipe_name == "Pilsen"


def test_invalid_status_raises_value_error():
    with pytest.raises(ValueError, match="status inv.lido"):
        RecipeState(status="not_a_real_status")


def test_save_and_load_round_trip(tmp_path):
    path = tmp_path / "recipe_state.json"
    original = RecipeState(
        recipe_name="Pilsen",
        status="holding",
        step_index=1,
        step_started_at=1000.0,
        hold_started_at=1500.0,
        hold_elapsed_seconds_at_pause=0.0,
    )
    original.save(path)

    loaded = RecipeState.load(path)
    assert loaded == original


def test_load_missing_file_returns_default_idle_state(tmp_path):
    state = RecipeState.load(tmp_path / "does_not_exist.json")
    assert state.status == "idle"


def test_save_overwrites_existing_file(tmp_path):
    path = tmp_path / "recipe_state.json"
    RecipeState.fresh("A").save(path)
    RecipeState.fresh("B").save(path)

    loaded = RecipeState.load(path)
    assert loaded.recipe_name == "B"


def test_pending_alarms_round_trip(tmp_path):
    from recipe_engine.state import AlarmEvent

    path = tmp_path / "recipe_state.json"
    original = RecipeState(
        status="holding",
        pending_alarms=[
            AlarmEvent(id=1, type="hop_addition", label="5kg Lupulo", fired_at=1000.0),
        ],
        next_alarm_id=2,
        fired_hop_alarm_keys=["3:0"],
    )
    original.save(path)

    loaded = RecipeState.load(path)
    assert loaded.pending_alarms == [AlarmEvent(id=1, type="hop_addition", label="5kg Lupulo", fired_at=1000.0)]
    assert loaded.next_alarm_id == 2
    assert loaded.fired_hop_alarm_keys == ["3:0"]


def test_pending_alarms_default_empty():
    state = RecipeState()
    assert state.pending_alarms == []
    assert state.next_alarm_id == 1
    assert state.fired_hop_alarm_keys == []
