"""건강 검진이 문제를 실제로 짚는지. 일부러 망가뜨린 데이터셋으로."""
from epokio.health import check


def make(tmp, train_n=40, val_n=2, broken=False, missing=0):
    for split, n in (("train", train_n), ("val", val_n)):
        (tmp / "images" / split).mkdir(parents=True)
        (tmp / "labels" / split).mkdir(parents=True)
        for i in range(n):
            (tmp / "images" / split / f"{i}.jpg").write_bytes(b"\xff\xd8\xff")
            if split == "train" and i < missing:
                continue
            row = "0 0.5 0.5 0.2 0.2" if i % 20 else "1 0.5 0.5 0.2 0.2"
            if broken and i == 0:
                row = "5 1.7 0.5 0.2 0.2"               # 없는 클래스 + 범위 밖 좌표
            (tmp / "labels" / split / f"{i}.txt").write_text(row + "\n")
    (tmp / "data.yaml").write_text(f"path: {tmp}\ntrain: images/train\nval: images/val\nnames:\n  0: cat\n  1: dog\n  2: bird\n")
    return tmp / "data.yaml"


def texts(r):
    return " ".join(w["text"] for w in r["warnings"])


def test_catches_tiny_val_missing_labels_zero_class_imbalance(tmp_path):
    r = check(str(make(tmp_path, missing=3)))
    t = texts(r)
    assert "Only 2 validation images" in t
    assert "3 train images have no label file" in t
    assert "No training examples for: bird" in t
    assert "unbalanced" in t
    assert r["score"] == "problems"


def test_catches_broken_rows(tmp_path):
    r = check(str(make(tmp_path, broken=True)))
    assert "broken" in texts(r)


def test_missing_yaml():
    r = check("/nope/data.yaml")
    assert r["ok"] is False and "nope" in r["error"]          # 어느 경로를 봤는지 말한다


def test_truncated_rows_and_fractional_classes_are_broken(tmp_path):
    """r[1:5]는 짧아도 오류가 안 나서 '0 0.5 0.5'가 멀쩡한 줄로 셌고, '1.7'은 1반으로 셌다."""
    y = make(tmp_path)
    (tmp_path / "labels" / "train" / "1.txt").write_text("0 0.5 0.5\n")
    (tmp_path / "labels" / "train" / "2.txt").write_text("1.7 0.5 0.5 0.2 0.2\n")
    assert check(str(y))["splits"]["train"]["bad_rows"] == 2


def test_a_class_only_in_validation_counts_as_missing(tmp_path):
    """전체로 세면 검증에만 있는 클래스가 '예시 있음'으로 넘어갔다. 학습에 없으면 배울 수 없다."""
    y = make(tmp_path, val_n=5)
    (tmp_path / "labels" / "val" / "0.txt").write_text("2 0.5 0.5 0.2 0.2\n")
    t = texts(check(str(y)))
    assert "only in val, not in train: bird" in t          # 맥 쪽 문장으로 합쳤다(같은 뜻)


def test_validation_images_copied_from_training_are_flagged(tmp_path):
    y = make(tmp_path, val_n=0)
    (tmp_path / "images" / "val").rmdir()
    import shutil
    shutil.copytree(tmp_path / "images" / "train", tmp_path / "images" / "val")   # 검증을 학습에서 그대로 복사
    for p in (tmp_path / "images" / "train").iterdir():                          # 크기를 파일마다 다르게(실제 사진처럼)
        p.write_bytes(b"\xff\xd8" + b"x" * int(p.stem))
        (tmp_path / "images" / "val" / p.name).write_bytes(b"\xff\xd8" + b"x" * int(p.stem))
    assert "val images are the same files as train images" in texts(check(str(y)))   # 내용 해시로 잡는다


def test_yaml_forms_ultralytics_accepts(tmp_path):
    """names: {0: a, 1: b} 는 빈 목록이 되어 클래스 검사가 꺼졌고, train: [a, b] 는 '이미지 없음'이었다."""
    y = make(tmp_path)
    y.write_text(f"path: {tmp_path}\ntrain: [images/train, images/val]\nval: images/val\nnames: {{0: cat, 1: dog, 2: bird}}\n")
    r = check(str(y))
    assert r["classes"] == ["cat", "dog", "bird"] and r["splits"]["train"]["images"] == 42


def test_a_folder_or_a_quoted_path_finds_the_yaml(tmp_path):
    """탐색기 '경로로 복사'는 따옴표를 씌운다. 폴더를 줘도 그 안의 data.yaml을 찾는다."""
    y = make(tmp_path)
    assert check(f'"{y}"')["ok"] and check(str(tmp_path))["data"] == str(y)


def test_same_name_and_size_but_different_pictures_is_not_a_leak(tmp_path):
    """분할마다 000001.bmp처럼 번호로 이름 짓고 압축을 안 하면 크기가 같다. 내용이 다르면 겹친 게 아니다."""
    y = make(tmp_path)
    for split, fill in (("train", b"a"), ("val", b"b")):
        for p in (tmp_path / "images" / split).iterdir():
            p.write_bytes(b"BM" + fill * 100)
    assert "same files as train images" not in texts(check(str(y)))


def test_datasets_ultralytics_downloads_are_not_blocked(tmp_path):
    """download: 가 있는 yaml은 첫 학습 때 받는다. '이미지 없음'을 오류로 두면 출발 전 점검이 멀쩡한 데이터셋을 막았다."""
    y = tmp_path / "coco128.yaml"
    y.write_text("path: ../datasets/coco128\ntrain: images/train2017\nval: images/train2017\nnames:\n  0: person\ndownload: https://example.invalid/coco128.zip\n")
    r = check(str(y))
    assert r["ok"] and all(w["level"] != "error" for w in r["warnings"])


def _ds(tmp, train, val, extra_yaml=""):
    """train/val: {이름: (이미지 바이트, 라벨 글)}"""
    for split, items in (("train", train), ("val", val)):
        (tmp / "images" / split).mkdir(parents=True)
        (tmp / "labels" / split).mkdir(parents=True)
        for name, (img, lab) in items.items():
            (tmp / "images" / split / f"{name}.jpg").write_bytes(img)
            (tmp / "labels" / split / f"{name}.txt").write_text(lab + "\n")
    (tmp / "data.yaml").write_text(f"path: {tmp}\ntrain: images/train\nval: images/val\nnames: [cat, dog]\n{extra_yaml}")
    return str(tmp / "data.yaml")


def jpg(i):
    return b"\xff\xd8\xff\xe0" + str(i).encode() * 10


BOX0, BOX1 = "0 0.5 0.5 0.2 0.2", "1 0.5 0.5 0.2 0.2"


def test_class_only_in_val_is_flagged(tmp_path):
    """전체 합으로 세면 dog가 '있음'이지만 train엔 없다. train 기준으로 본다"""
    t = texts(check(_ds(tmp_path, {f"t{i}": (jpg(i), BOX0) for i in range(5)}, {"v0": (jpg(99), BOX1)})))
    assert "only in val, not in train: dog" in t and "No training examples" not in t


def test_train_val_overlap_by_content_and_by_name(tmp_path):
    t = texts(check(_ds(tmp_path / "a", {f"t{i}": (jpg(i), BOX0) for i in range(5)}, {"other": (jpg(0), BOX0)})))
    assert "1 val images are the same files as train images" in t
    t = texts(check(_ds(tmp_path / "b", {f"t{i}": (jpg(i), BOX0) for i in range(5)}, {"t1": (jpg(50), BOX0)})))
    assert "same file name as a train image (for example t1)" in t


def test_duplicate_and_unreadable_images(tmp_path):
    train = {f"t{i}": (jpg(i), BOX0) for i in range(5)}
    train["copy"] = (jpg(2), BOX0)
    train["notimg"] = (b"hello, not an image", BOX0)
    train["empty"] = (b"", BOX0)
    t = texts(check(_ds(tmp_path, train, {"v": (jpg(9), BOX0)})))
    assert "1 images are exact copies" in t and "2 image files are empty or not a known image format" in t


def test_pose_row_length_checked_against_kpt_shape(tmp_path):
    ok = "0 0.5 0.5 0.2 0.2 0.1 0.1 2 0.2 0.2 1"                 # kpt_shape [2, 3] = 5 + 6
    short = "0 0.5 0.5 0.2 0.2 0.1 0.1 2"
    r = check(_ds(tmp_path, {"a": (jpg(1), ok), "b": (jpg(2), short)}, {"v": (jpg(3), ok)}, "kpt_shape: [2, 3]\n"))
    assert r["splits"]["train"]["bad_rows"] == 1 and r["splits"]["val"]["bad_rows"] == 0


def test_seg_polygon_all_points_range_checked(tmp_path):
    good = "0 0.1 0.1 0.9 0.1 0.5 0.9"
    far = "0 0.1 0.1 0.9 0.1 0.5 1.4"                            # 앞 4칸은 멀쩡, 마지막 점만 밖
    odd = "0 0.1 0.1 0.9 0.1 0.5"                                # 좌표 개수가 홀수
    r = check(_ds(tmp_path, {"a": (jpg(1), good), "b": (jpg(2), far), "c": (jpg(4), odd)}, {"v": (jpg(3), good)}))
    assert r["splits"]["train"]["bad_rows"] == 2


def test_deep_limit_samples_and_says_so(tmp_path):
    train = {f"t{i}": (jpg(i), BOX0) for i in range(6)}
    train["zz_copy"] = (jpg(0), BOX0)                             # 정렬상 뒤쪽이라 한도 밖
    d = _ds(tmp_path, train, {"v": (jpg(9), BOX0)})
    r = check(d, deep_limit=3)
    assert "Checked the contents of 4 of 8 images" in " ".join(r["tips"]) and "exact copies" not in texts(r)
    assert "1 images are exact copies" in texts(check(d, deep_limit=None, full_hash=True))
