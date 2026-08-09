"""Regression boundaries for generic sandbox bootstrap assets."""

from pathlib import Path

from ptc_agent.core.sandbox._shared import (
    _SANDBOX_INTERNAL_PACKAGES,
    _internal_package_files,
)


def test_finance_protocol_packages_are_not_sandbox_internal_packages():
    """Generic sandboxes must not carry the retired financial data runtime."""
    assert "data_client" not in _SANDBOX_INTERNAL_PACKAGES
    assert "market_protocol" not in _SANDBOX_INTERNAL_PACKAGES


def test_internal_package_sync_skips_retired_finance_packages(tmp_path: Path):
    """The manifest uploader must omit finance packages even when they exist."""
    src_dir = tmp_path / "src"
    src_dir.mkdir()
    (src_dir / "__init__.py").write_text("")
    for package in ("data_client", "market_protocol"):
        package_dir = src_dir / package
        package_dir.mkdir()
        (package_dir / "__init__.py").write_text("")
        (package_dir / "seed.json").write_text("{}")

    uploaded_paths = {
        relative_path for _local_path, relative_path in _internal_package_files(src_dir)
    }

    assert uploaded_paths == {Path("__init__.py")}


def test_sandbox_dockerfile_handles_flaky_http_apt_proxy_requests():
    """The local sandbox build must tolerate transient Docker proxy failures."""
    dockerfile = (
        Path(__file__).resolve().parents[5] / "Dockerfile.sandbox"
    ).read_text()

    assert 'Acquire::http::No-Cache "true";' in dockerfile
    assert 'Acquire::http::Pipeline-Depth "0";' in dockerfile
    assert 'Acquire::Retries "10";' in dockerfile


def test_sandbox_dockerfile_uses_reachable_ubuntu_ports_mirror():
    """The local Docker build must select the validated ARM Ubuntu mirror first."""
    dockerfile = (
        Path(__file__).resolve().parents[5] / "Dockerfile.sandbox"
    ).read_text()

    mirror_command = (
        "sed -i 's|http://ports.ubuntu.com/ubuntu-ports|"
        "http://mirrors.ustc.edu.cn/ubuntu-ports|g'"
    )
    assert mirror_command in dockerfile
    assert dockerfile.index(mirror_command) < dockerfile.index("apt-get update")
