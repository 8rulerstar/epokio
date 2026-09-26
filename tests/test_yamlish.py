"""data.yaml 읽기: PyYAML 있음/없음 두 경로. 예시 yaml은 Ultralytics 형식을 흉내 내 직접 쓴 것."""
import sys
import types
from pathlib import Path

import pytest

from epokio import health, yamlish

FIX = Path(__file__).parent / "fixtures" / "data_yaml"
ALL = sorted(p.name for p in FIX.glob("*.yaml"))


@pytest.fixture
def no_pyyaml(monkeypatch):
    monkeypatch.setitem(sys.modules, "yaml", None)      # import yaml -> ImportError


def cfg_of(name):
    return health._parse_yaml((FIX / name).read_text(encoding="utf-8"))


EXPECT = {
    "det_dict_names.yaml": ({"path": "../datasets/toy", "train": "images/train", "val": "images/val"},
                            ["person", "bicycle", "traffic light", "fire hydrant"]),
    "pose_kpt.yaml": ({"path": "toy-pose", "kpt_shape": [17, 3]}, ["person"]),
    "list_train_block.yaml": ({"train": ["images/train2012", "images/train2007"], "val": ["images/test2007"]},
                              ["aeroplane", "bicycle"]),
    "flow_everything.yaml": ({"path": "toy dir", "train": ["images/a", "images/b"], "val": "images/val"},
                             ["cat", "dog", "hot dog"]),
    "names_list_multiline.yaml": ({"train": "images/train"}, ["cat", "dog", "bird"]),
    "nested_indent.yaml": ({"val": "images/val"}, ["a#b", "c"]),
    "nc_only.yaml": ({"train": "images/train"}, ["class_0", "class_1"]),
}


@pytest.mark.parametrize("name", ALL)
def test_fallback_reads_common_forms(name, no_pyyaml):
    cfg, _ = cfg_of(name)
    fields, names = EXPECT[name]
    for k, v in fields.items():
        assert cfg[k] == v, (name, k)
    assert cfg["names"] == names
    assert "test" not in cfg                             # 빈 test: 는 없는 것으로


def test_fallback_warns_instead_of_guessing(no_pyyaml):
    data, warns = yamlish.load((FIX / "nested_indent.yaml").read_text())
    assert "download" not in data and any("download" in w for w in warns)
    assert data["extra"] == {"deep": {"list": [1, 2.5, None, True]}}
    for bad in ("a: &x 1\nb: *x\n", "a: !tag 1\n", "\ta: 1\n", "- k: v\n"):
        _, w = yamlish.load(bad, use_pyyaml=False)
        assert w, bad
    assert yamlish.load("", use_pyyaml=False) == ({}, [])


def test_fallback_scalars_and_quotes():
    d, w = yamlish.load("a: 'it''s'\nb: \"x # y\"\nc: 1e-3\nd: ~\ne: 3\nf: C:\\data\\x\n", use_pyyaml=False)
    assert not w
    assert d == {"a": "it's", "b": "x # y", "c": 0.001, "d": None, "e": 3, "f": "C:\\data\\x"}


def test_uses_pyyaml_when_present(monkeypatch):
    fake = types.ModuleType("yaml")
    fake.YAMLError = type("YAMLError", (Exception,), {})
    fake.safe_load = lambda text: {"train": "t", "val": "v", "names": {0: "only"}}
    monkeypatch.setitem(sys.modules, "yaml", fake)
    cfg, warns = health._parse_yaml("anything")
    assert cfg["names"] == ["only"] and not warns

    def boom(text):
        raise fake.YAMLError("bad thing\nat line 3")
    fake.safe_load = boom
    cfg, warns = health._parse_yaml("x")
    assert cfg == {} and warns == ["YAML could not be read: bad thing"]


@pytest.mark.parametrize("name", ALL)
def test_fallback_matches_real_pyyaml(name):
    yaml = pytest.importorskip("yaml")
    text = (FIX / name).read_text(encoding="utf-8")
    real = yaml.safe_load(text)
    mine, _ = yamlish.load(text, use_pyyaml=False)
    real.pop("download", None)                          # 폴백은 블록 문자열을 경고와 함께 뺀다
    assert mine == real


def test_health_check_reads_list_train_and_warns(tmp_path, no_pyyaml):
    for sub in ("a", "b", "v"):
        (tmp_path / "images" / sub).mkdir(parents=True)
        (tmp_path / "labels" / sub).mkdir(parents=True)
        (tmp_path / "images" / sub / "1.jpg").write_bytes(b"\xff\xd8\xff")
        (tmp_path / "labels" / sub / "1.txt").write_text("0 0.5 0.5 0.2 0.2\n", encoding="utf-8")
    y = tmp_path / "data.yaml"
    y.write_text(f"path: {tmp_path}\ntrain: [images/a, images/b]\nval: images/v\n"
                 "names: {0: cat}\nx: &anchor 1\n", encoding="utf-8")
    r = health.check(str(y))
    assert r["splits"]["train"]["images"] == 2 and r["classes"] == ["cat"]
    assert any("'&'" in w["text"] for w in r["warnings"])


def test_image_list_txt_is_utf8(tmp_path):
    img = tmp_path / "사진 폴더" / "고양이.jpg"
    img.parent.mkdir()
    img.write_bytes(b"\xff\xd8\xff")
    lst = tmp_path / "train.txt"
    lst.write_bytes(("\ufeff" + str(img) + "\n").encode("utf-8"))
    assert health._images_of(str(lst), tmp_path) == [img]
