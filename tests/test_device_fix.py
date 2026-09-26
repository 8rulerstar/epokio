"""다시 학습으로 옮겨 온 device가 이 자리에서 뜻이 없을 때(gpus.fix_device)"""
from epokio import gpus


def test_cuda_index_dropped_on_machine_without_cuda():
    """CUDA 기계의 학습을 맥에서 다시 돌리면 device=0이 와서 실패했다"""
    p = {"device": 0, "epochs": 3}
    assert gpus.fix_device(p, "auto", None, has_cuda=False)
    assert "device" not in p and p["epochs"] == 3


def test_masked_gpu_becomes_zero():
    """대기열이 GPU 3번만 보이게 하면 자식 안에서는 0번 한 장이다"""
    for d in (1, "1", "cuda:1", "0,1"):
        p = {"device": d}
        assert gpus.fix_device(p, "auto", 3, has_cuda=True)
        assert p["device"] == 0, d


def test_cpu_lane_forces_cpu():
    p = {"device": 0}
    assert gpus.fix_device(p, gpus.CPU, None, has_cuda=True)
    assert p["device"] == "cpu"


def test_non_gpu_values_and_single_gpu_untouched():
    for d in ("cpu", "mps", None, ""):
        p = {"device": d}
        assert gpus.fix_device(p, "auto", None, has_cuda=False) is None
        assert p == {"device": d}
    p = {"device": 0}                         # GPU 한 장, 자리 배정 없음: 같은 기계의 다시 학습은 그대로
    assert gpus.fix_device(p, "auto", None, has_cuda=True) is None and p["device"] == 0


def test_build_command_applies_fix_without_touching_saved_params(tmp_path, monkeypatch):
    from epokio import jobs
    monkeypatch.setattr(jobs, "SCRIPTS", tmp_path)
    monkeypatch.setattr(jobs, "HOME", tmp_path)
    monkeypatch.setattr(gpus, "listed", lambda refresh=False: [])
    j = jobs.Job(id="t1", kind="train", name="t", python="python3",
                 params={"model": "yolo11n.pt", "data": "coco8.yaml", "device": 0},
                 log=str(tmp_path / "t1.log"))
    cmd = jobs.build_command(j)
    script = open(cmd[-1], encoding="utf-8").read()
    assert '"device": 0' not in script and '"data": "coco8.yaml"' in script
    assert j.params["device"] == 0                 # 저장된 요청은 그대로(기록이 바뀌지 않게)
    assert "no CUDA GPU" in open(j.log, encoding="utf-8").read()
