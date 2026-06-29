from failsafe_coercion import coerce_value


def test_coerce_pwm_string_to_float():
    assert coerce_value("0", "pwm") == 0.0
    assert coerce_value("75.5", "pwm") == 75.5


def test_coerce_analog_string_with_comma_decimal():
    assert coerce_value("25,5", "analog") == 25.5


def test_coerce_pwm_already_float_passthrough():
    assert coerce_value(42.0, "pwm") == 42.0


def test_coerce_digital_true_strings():
    for value in ("true", "TRUE", "1", "on", "Yes"):
        assert coerce_value(value, "digital") is True


def test_coerce_digital_false_strings():
    for value in ("false", "0", "off", "", "no"):
        assert coerce_value(value, "digital") is False


def test_coerce_digital_already_bool_passthrough():
    assert coerce_value(True, "digital") is True
    assert coerce_value(False, "digital") is False


def test_coerce_unknown_subtype_defaults_to_bool():
    assert coerce_value("true", None) is True
    assert coerce_value("false", "weird_subtype") is False
