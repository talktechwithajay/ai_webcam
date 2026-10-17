import pytest

from ahv.config import ConfigError, mask_url, parse_config, validate_for_run


def test_recorder_url_encodes_special_characters():
    cfg = parse_config({"recorder": {"host": "192.168.1.108", "username": "view", "password": "p@ss:w/rd#1"},
                        "cameras": {"front_door": {"role": "front", "source": "recorder", "channel": 3}}})
    url = cfg.camera_url(cfg.cameras[0])
    assert url == "rtsp://view:p%40ss%3Aw%2Frd%231@192.168.1.108:554/cam/realmonitor?channel=3&subtype=1"
    assert cfg.camera_url(cfg.cameras[0], 0).endswith("channel=3&subtype=0")


def test_mask_url_hides_credentials():
    assert "secret" not in mask_url("rtsp://admin:secret@10.0.0.2:554/x")


def test_unknown_keys_and_bad_role_rejected():
    with pytest.raises(ConfigError):
        parse_config({"dashboard": {"pasword": "x"}})
    with pytest.raises(ConfigError):
        parse_config({"cameras": {"a": {"role": "garage"}}})
    with pytest.raises(ConfigError):
        parse_config({"cameras": {"a": {"role": "front", "zone": [0, 0, 2, 1]}}})


def test_default_password_blocks_start(monkeypatch):
    monkeypatch.delenv("AHV_ALLOW_DEFAULT_PASSWORD", raising=False)
    assert any("password" in p for p in validate_for_run(parse_config({"dashboard": {"password": "change-me"}})))
    assert validate_for_run(parse_config({"dashboard": {"password": "a-real-one"}})) == []


def test_recorder_camera_needs_host():
    cfg = parse_config({"dashboard": {"password": "x1"}, "cameras": {"f": {"role": "front", "source": "recorder"}}})
    assert any("recorder.host" in p for p in validate_for_run(cfg))


def test_custom_rtsp_template():
    cfg = parse_config({"recorder": {"host": "h", "username": "u", "password": "p",
                                     "rtsp_url_template": "rtsp://{username}:{password}@{host}:{port}/ch{channel}/{subtype}"},
                        "cameras": {"f": {"role": "front", "source": "recorder", "channel": 2}}})
    assert cfg.camera_url(cfg.cameras[0]) == "rtsp://u:p@h:554/ch2/1"
