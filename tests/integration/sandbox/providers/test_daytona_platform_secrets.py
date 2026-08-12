"""Live Daytona Secret tests: placeholder mount, egress substitution, host restriction, rotation.

The test uses an explicitly configured HTTPS endpoint that authenticates the
provided test secret. A placeholder must fail there, while Daytona's egress
substitution allows the configured secret to succeed. Echo services are not
suitable because substitution only happens in request headers.
"""

from __future__ import annotations

import asyncio
import json
import os
import shlex
import uuid
from urllib.parse import urlparse

import pytest

from ptc_agent.config.core import DaytonaConfig
from ptc_agent.core.sandbox.platform_secrets import (
    PlatformSecretDefinition,
    ResolvedPlatformSecret,
)
from ptc_agent.core.sandbox.providers.daytona import DaytonaProvider


pytestmark = [
    pytest.mark.integration,
    pytest.mark.provider_daytona,
    pytest.mark.asyncio,
    pytest.mark.skipif(
        "daytona"
        not in os.getenv(
            "SANDBOX_TEST_PROVIDERS",
            os.getenv("SANDBOX_TEST_PROVIDER", "memory"),
        )
        .lower()
        .split(","),
        reason="requires Daytona provider",
    ),
]

def _required_env(name: str) -> str:
    value = os.getenv(name, "")
    if not value:
        pytest.skip(f"{name} is required for the live Daytona Secret test")
    return value


def _probe_config() -> tuple[str, str, str, int]:
    """Return the endpoint contract for an approved live substitution probe."""
    endpoint = _required_env("PLATFORM_SECRET_PROBE_URL")
    header = os.getenv("PLATFORM_SECRET_PROBE_HEADER", "Authorization")
    try:
        success_status = int(os.getenv("PLATFORM_SECRET_PROBE_SUCCESS_STATUS", "200"))
    except ValueError as exc:
        raise RuntimeError("PLATFORM_SECRET_PROBE_SUCCESS_STATUS must be an integer") from exc

    parsed = urlparse(endpoint)
    if parsed.scheme != "https" or not parsed.hostname:
        raise RuntimeError("PLATFORM_SECRET_PROBE_URL must be an absolute HTTPS URL")
    return endpoint, header, parsed.hostname, success_status


def _resolved(
    *,
    env_var: str,
    name: str,
    value: str,
    hosts: tuple[str, ...],
) -> tuple[ResolvedPlatformSecret, ...]:
    definition = PlatformSecretDefinition(
        source_env_var=env_var,
        sandbox_env_var=env_var,
        name_suffix=name,
        description="LangAlpha Daytona Secret integration test",
        hosts=hosts,
    )
    return (ResolvedPlatformSecret(definition=definition, name=name, value=value),)


def _probe_command(
    env_var: str, *, endpoint: str, header: str, success_status: int
) -> str:
    """Issue the configured request with the secret in its approved header.

    Emits only booleans and the HTTP status — never the key or placeholder.
    """
    code = f"""
import json, os, urllib.error, urllib.request
key = os.environ[{env_var!r}]
request = urllib.request.Request(
    {endpoint!r},
    headers={{{header!r}: key}},
)
try:
    with urllib.request.urlopen(request, timeout=30) as response:
        status = response.status
except urllib.error.HTTPError as e:
    status = e.code
except urllib.error.URLError:
    status = 0
ok = status == {success_status}
print(json.dumps({{'placeholder': key.startswith('dtn_secret_'), 'status': status, 'ok': ok}}))
"""
    return f"python3 -c {shlex.quote(code)}"


def _provider() -> DaytonaProvider:
    api_key = _required_env("DAYTONA_API_KEY")
    base_url = os.getenv("DAYTONA_BASE_URL", "https://app.daytona.io/api")
    return DaytonaProvider(
        DaytonaConfig(api_key=api_key, base_url=base_url, snapshot_enabled=False)
    )


async def _probe(runtime, env_var: str, probe: tuple[str, str, str, int]) -> dict:
    endpoint, header, _, success_status = probe
    result = await runtime.exec(
        _probe_command(
            env_var,
            endpoint=endpoint,
            header=header,
            success_status=success_status,
        )
    )
    return json.loads(result.stdout)


async def test_substitution_and_rotation_through_configured_probe():
    """A placeholder fails; the rotated configured key succeeds without recreation.

    The failure -> success transition proves substitution and rotation in one
    signal: an unsubstituted placeholder cannot authenticate the request.
    """
    platform_key = _required_env("PLATFORM_SECRET_API_KEY")
    probe = _probe_config()
    _, _, probe_host, success_status = probe
    provider = _provider()
    runtime = None
    identity = None
    name = f"langalpha_test_{uuid.uuid4().hex}"
    junk = uuid.uuid4().hex
    try:
        identity = (
            await provider.reconcile_platform_secrets(
                _resolved(
                    env_var="PLATFORM_SECRET_API_KEY", name=name, value=junk, hosts=(probe_host,)
                )
            )
        )[0]
        runtime = await provider.create(platform_secret_bindings={"PLATFORM_SECRET_API_KEY": name})

        env_result = await runtime.exec(
            "python3 -c 'import os; print(os.environ[\"PLATFORM_SECRET_API_KEY\"])'"
        )
        placeholder = env_result.stdout.strip()
        assert placeholder == identity.placeholder
        assert placeholder.startswith("dtn_secret_")
        assert placeholder != junk
        assert placeholder != platform_key

        before = await _probe(runtime, "PLATFORM_SECRET_API_KEY", probe)
        assert before["placeholder"] is True
        assert before["ok"] is False

        rotated_identity = (
            await provider.reconcile_platform_secrets(
                _resolved(
                    env_var="PLATFORM_SECRET_API_KEY", name=name, value=platform_key, hosts=(probe_host,)
                )
            )
        )[0]
        assert rotated_identity.placeholder == placeholder

        # Rotation propagates through the egress layer asynchronously
        # (~30s observed live), so allow a 90s window.
        after = None
        for _ in range(30):
            after = await _probe(runtime, "PLATFORM_SECRET_API_KEY", probe)
            if after["status"] == success_status:
                break
            await asyncio.sleep(3)
        assert after == {"placeholder": True, "status": success_status, "ok": True}
    finally:
        try:
            if runtime is not None:
                await runtime.delete()
        finally:
            try:
                if identity is not None:
                    await provider._client.secret.delete(identity.provider_secret_id)
            finally:
                await provider.close()


async def test_hot_identity_swap_reaches_new_processes_without_restart():
    """Identity swap via remount on a RUNNING sandbox — no restart needed.

    The restart-free half of convergence: after ``update_secrets`` a fresh
    exec process sees the NEW placeholder immediately, and egress substitutes
    it (a failing placeholder baseline -> a successful configured secret). This is the
    assumption the request-path hot resync and the sweep's certified-behind
    branch stand on (probe run 2026-07-23 measured 0s to first 200).
    """
    import hashlib

    from ptc_agent.core.sandbox.platform_secrets import (
        remount_platform_secret_bindings,
    )

    platform_key = _required_env("PLATFORM_SECRET_API_KEY")
    probe = _probe_config()
    _, _, probe_host, success_status = probe
    provider = _provider()
    runtime = None
    identity_a = identity_b = None
    name_a = f"langalpha_test_a_{uuid.uuid4().hex}"
    name_b = f"langalpha_test_b_{uuid.uuid4().hex}"
    junk = uuid.uuid4().hex
    try:
        # Secret A: junk value (401 oracle). Secret B: real key (200 oracle).
        identity_a = (
            await provider.reconcile_platform_secrets(
                _resolved(
                    env_var="PLATFORM_SECRET_API_KEY", name=name_a, value=junk, hosts=(probe_host,)
                )
            )
        )[0]
        identity_b = (
            await provider.reconcile_platform_secrets(
                _resolved(
                    env_var="PLATFORM_SECRET_API_KEY",
                    name=name_b,
                    value=platform_key,
                    hosts=(probe_host,),
                )
            )
        )[0]
        assert identity_a.placeholder != identity_b.placeholder
        runtime = await provider.create(
            platform_secret_bindings={"PLATFORM_SECRET_API_KEY": name_a}
        )

        before = await _probe(runtime, "PLATFORM_SECRET_API_KEY", probe)
        assert before["placeholder"] is True
        assert before["ok"] is False

        # Hot swap A -> B on the running sandbox; no stop/start anywhere.
        await remount_platform_secret_bindings(
            runtime,
            expected={
                "PLATFORM_SECRET_API_KEY": hashlib.sha256(
                    identity_b.placeholder.encode()
                ).hexdigest()
            },
            bindings={"PLATFORM_SECRET_API_KEY": name_b},
        )

        env_result = await runtime.exec(
            "python3 -c 'import os; print(os.environ[\"PLATFORM_SECRET_API_KEY\"])'"
        )
        assert env_result.stdout.strip() == identity_b.placeholder

        after = None
        for _ in range(30):
            after = await _probe(runtime, "PLATFORM_SECRET_API_KEY", probe)
            if after["status"] == success_status:
                break
            await asyncio.sleep(3)
        assert after == {"placeholder": True, "status": success_status, "ok": True}
    finally:
        try:
            if runtime is not None:
                await runtime.delete()
        finally:
            try:
                for identity in (identity_a, identity_b):
                    if identity is not None:
                        await provider._client.secret.delete(
                            identity.provider_secret_id
                        )
            finally:
                await provider.close()


async def test_host_restriction_blocks_substitution():
    """A Secret allowed only for another host must not be substituted.

    Uses the real key as the value so a restriction failure is observable as
    an improper successful response; the value can only reach approved hosts.
    """
    platform_key = _required_env("PLATFORM_SECRET_API_KEY")
    probe = _probe_config()
    provider = _provider()
    runtime = None
    identity = None
    name = f"langalpha_test_{uuid.uuid4().hex}"
    try:
        identity = (
            await provider.reconcile_platform_secrets(
                _resolved(
                    env_var="PLATFORM_SECRET_API_KEY",
                    name=name,
                    value=platform_key,
                    hosts=("unapproved.invalid",),
                )
            )
        )[0]
        runtime = await provider.create(platform_secret_bindings={"PLATFORM_SECRET_API_KEY": name})

        result = await _probe(runtime, "PLATFORM_SECRET_API_KEY", probe)
        assert result["placeholder"] is True
        assert result["ok"] is False
    finally:
        try:
            if runtime is not None:
                await runtime.delete()
        finally:
            try:
                if identity is not None:
                    await provider._client.secret.delete(identity.provider_secret_id)
            finally:
                await provider.close()
