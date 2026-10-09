"""results.csv 캐시: 도는 학습은 붙은 줄만 읽고, 결과는 늘 처음부터 읽은 것과 같아야 한다.
★2초 안에 바뀐 파일을 매번 통째로 다시 읽어, 2만 줄 학습이 도는 동안 /run 한 번이 1.6초, agent가 쉬어도 CPU 9%였다.
★모든 학습의 행을 들고 있어 학습 1,000개면 agent가 270MB였다."""
import os
import time

from epokio import adapters_base as ab

HEAD = "epoch,time,train/box_loss,metrics/mAP50-95(B)\n"


def fresh(p):
    ab._CSV_CACHE.pop(p, None)
    return ab._read_csv(p)


def row(e):
    return f"{e},{e * 3.0},{1.5 - e * 0.001:.4f},{0.1 + e * 0.0001:.4f}\n"


def test_appended_rows_match_a_full_read(tmp_path):
    p = tmp_path / "results.csv"
    p.write_text(HEAD + "".join(row(e) for e in range(1, 2001)), encoding="utf-8")
    assert len(ab._read_csv(p)) == 2000
    parsed = []
    real = ab._dict_rows
    ab._dict_rows = lambda f, rows: (lambda out: (parsed.append(len(out)), out)[1])(real(f, rows))
    try:
        for e in range(2001, 2006):
            with p.open("a", encoding="utf-8") as fh:
                fh.write(row(e))
            parsed.clear()
            got = ab._read_csv(p)
            assert parsed == [1]                       # 붙은 한 줄만 읽었다(예전엔 2,000줄 넘게 다시)
            assert len(got) == e and got == fresh(p)
            parsed.clear()
            ab._read_csv(p)
            assert parsed == []                        # 그대로면(2초 안이어도) 다시 읽지 않는다
    finally:
        ab._dict_rows = real


def test_half_written_line_then_completed(tmp_path):
    p = tmp_path / "results.csv"
    p.write_text(HEAD + row(1) + "2,6.0,1.4", encoding="utf-8")       # 쓰는 중인 끝 줄은 버린다
    assert [r["epoch"] for r in ab._read_csv(p)] == ["1"]
    with p.open("a", encoding="utf-8") as fh:
        fh.write("98,0.1002\n")
    got = ab._read_csv(p)
    assert [r["epoch"] for r in got] == ["1", "2"] and got[1]["train/box_loss"] == "1.498" and got == fresh(p)


def test_same_size_rewrite_within_two_seconds_is_seen(tmp_path):
    p = tmp_path / "results.csv"
    p.write_text(HEAD + row(1), encoding="utf-8")
    ab._read_csv(p)
    p.write_text(HEAD.replace("metrics/mAP50-95(B)", "metrics/mAP50-95(M)") + row(1), encoding="utf-8")
    st = p.stat()
    assert "metrics/mAP50-95(M)" in ab._read_csv(p)[0] and st.st_size == p.stat().st_size


def test_line_continued_after_an_old_file_without_newline(tmp_path):
    p = tmp_path / "results.csv"
    p.write_text(HEAD + row(1) + "2,6.0,1.4", encoding="utf-8")
    old = time.time() - 60
    os.utime(p, (old, old))                                            # 오래된 파일: 끝 줄도 읽는다
    assert len(ab._read_csv(p)) == 2
    with p.open("a", encoding="utf-8") as fh:
        fh.write("98,0.1002\n")
    got = ab._read_csv(p)
    assert got == fresh(p) and len(got) == 2 and got[1]["train/box_loss"] == "1.498"


def test_dictreader_rules_kept(tmp_path):
    p = tmp_path / "results.csv"
    p.write_bytes("﻿epoch, a ,b\n1,2\n\n2,3,4,5\n".encode("utf-8"))
    assert ab._read_csv(p) == [{"epoch": "1", "a": "2", "b": ""}, {"epoch": "2", "a": "3", "b": "4"}]
    with p.open("a", encoding="utf-8") as fh:
        fh.write("3, 7 ,8\n")
    assert ab._read_csv(p)[-1] == {"epoch": "3", "a": "7", "b": "8"} and ab._read_csv(p) == fresh(p)


def test_cache_is_bounded(tmp_path):
    for i in range(ab._CSV_KEEP + 40):
        p = tmp_path / f"r{i}.csv"
        p.write_text(HEAD + row(1), encoding="utf-8")
        ab._read_csv(p)
    assert len(ab._CSV_CACHE) <= ab._CSV_KEEP
