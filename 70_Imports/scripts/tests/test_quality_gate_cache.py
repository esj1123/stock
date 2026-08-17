from pathlib import Path
import sys

sys.path.append(str(Path(__file__).resolve().parents[3] / 'scripts'))

from quality_gate import run_command


def test_run_command_preserves_environment_and_prevents_python_cache_artifacts(tmp_path: Path, monkeypatch):
    synthetic_repo = tmp_path / "synthetic_repo"
    synthetic_repo.mkdir()
    (synthetic_repo / "synthetic_cache_module.py").write_text("VALUE = 7\n", encoding="utf-8")
    (synthetic_repo / "test_synthetic_cache.py").write_text(
        "import synthetic_cache_module\n\n"
        "def test_value():\n"
        "    assert synthetic_cache_module.VALUE == 7\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("STOCK_QUALITY_GATE_ENV_SENTINEL", "preserved")

    code, output = run_command(
        [
            sys.executable,
            "-c",
            "import os, synthetic_cache_module; "
            "print(os.environ.get('STOCK_QUALITY_GATE_ENV_SENTINEL')); "
            "print(synthetic_cache_module.VALUE)",
        ],
        synthetic_repo,
    )

    assert code == 0
    assert output.splitlines() == ["preserved", "7"]

    code, output = run_command(
        [
            sys.executable,
            "-m",
            "pytest",
            "-p",
            "no:cacheprovider",
            "--basetemp",
            str(tmp_path / "pytest_subprocess"),
            "test_synthetic_cache.py",
        ],
        synthetic_repo,
    )

    assert code == 0, output
    cache_artifacts = [
        path
        for path in synthetic_repo.rglob("*")
        if path.name in {"__pycache__", ".pytest_cache"} or path.suffix == ".pyc"
    ]
    assert cache_artifacts == []
