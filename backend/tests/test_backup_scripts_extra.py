"""More backup/restore behaviour (QOS-0101): the GPG path, cleanup on failure, the staleness alert
script and restore across formats. Uses the same stub-binary harness as test_backup_scripts.py."""

from __future__ import annotations

import gzip
import os
import subprocess
import time

import pytest

from tests.test_backup_scripts import (  # noqa: F401  (env is a pytest fixture)
    BACKUP,
    RESTORE,
    ROOT,
    SH,
    _shim,
    _sh_path,
    dumps,
    env,  # noqa: F811 - re-exported pytest fixture, used by name as a test argument
    run,
)

pytestmark = pytest.mark.skipif(SH is None, reason="needs a POSIX sh")

CHECK_AGE = ROOT / "scripts" / "check_backup_age.sh"


def _stub_gpg(tmp_path, e, fail=False):
    bindir = tmp_path / "bin"
    # gpg --batch --yes --encrypt --recipient R --output OUT IN     |    gpg --batch --decrypt IN
    body = (
        'if [ "${FAKE_GPG_FAIL:-0}" = "1" ]; then echo "gpg: boom" >&2; exit 2; fi\n'
        'for a in "$@"; do if [ "$a" = "--decrypt" ]; then DEC=1; fi; done\n'
        'if [ "${DEC:-0}" = "1" ]; then eval "LAST=\\${$#}"; cat "$LAST"; exit 0; fi\n'
        'OUT=""; PREV=""\n'
        'for a in "$@"; do if [ "$PREV" = "--output" ]; then OUT="$a"; fi; PREV="$a"; done\n'
        'eval "IN=\\${$#}"; cp "$IN" "$OUT"\n'
    )
    _shim(bindir, "gpg", body)
    # Git Bash resolves `gpg` to gpg.exe and ignores an extensionless stub on PATH.
    e["GPG_BIN"] = _sh_path(bindir / "gpg")


def _age_of(path, seconds):
    t = time.time() - seconds
    os.utime(path, (t, t))


# --- GPG path -----------------------------------------------------------------------

def test_gpg_recipient_produces_a_gpg_file_and_records_success(env, tmp_path):
    e, backups, _ = env
    _stub_gpg(tmp_path, e)
    r = run(BACKUP, e, BACKUP_GPG_RECIPIENT="ops@example.test")
    assert r.returncode == 0, r.stderr
    (name,) = dumps(backups)
    assert name.endswith(".sql.gz.gpg")
    assert (backups / "LAST_SUCCESS").read_text().split()[1] == name


def test_encryption_failure_is_fatal_and_leaves_no_partial_or_plain_file(env, tmp_path):
    e, backups, _ = env
    _stub_gpg(tmp_path, e)
    r = run(BACKUP, e, BACKUP_GPG_RECIPIENT="ops@example.test", FAKE_GPG_FAIL="1")
    assert r.returncode != 0 and "gpg encryption failed" in r.stderr
    assert dumps(backups) == []
    assert not list(backups.glob(".bizboard-*")), "no partial file may survive"
    assert not (backups / "LAST_SUCCESS").exists()


def test_a_recipient_takes_precedence_over_the_unencrypted_escape_hatch(env, tmp_path):
    e, backups, _ = env
    _stub_gpg(tmp_path, e)
    r = run(BACKUP, e, BACKUP_GPG_RECIPIENT="ops@example.test", BACKUP_ALLOW_UNENCRYPTED="1")
    assert r.returncode == 0
    assert dumps(backups)[0].endswith(".gpg"), "allowing plaintext must never downgrade a configured recipient"


# --- failure hygiene --------------------------------------------------------------------

def test_failed_offsite_copy_keeps_the_local_file_but_does_not_claim_success(env):
    e, backups, _ = env
    r = run(BACKUP, e, BACKUP_ALLOW_UNENCRYPTED="1", BACKUP_OFFSITE_CMD="exit 9")
    assert r.returncode != 0
    assert len(dumps(backups)) == 1, "the good local dump is kept for manual recovery"
    assert "local file kept" in r.stderr
    assert not (backups / "LAST_SUCCESS").exists()


def test_a_second_run_after_a_failed_one_succeeds_and_does_not_reuse_partials(env):
    e, backups, _ = env
    assert run(BACKUP, e, BACKUP_ALLOW_UNENCRYPTED="1", FAKE_PG_FAIL="1").returncode != 0
    time.sleep(1.1)  # file names carry a one-second timestamp
    ok = run(BACKUP, e, BACKUP_ALLOW_UNENCRYPTED="1")
    assert ok.returncode == 0, ok.stderr
    assert len(dumps(backups)) == 1 and not list(backups.glob(".bizboard-*"))


def test_retention_never_touches_unrelated_files(env):
    e, backups, _ = env
    backups.mkdir()
    other = backups / "notes.txt"
    other.write_text("keep me")
    _age_of(other, 400 * 86400)
    r = run(BACKUP, e, BACKUP_ALLOW_UNENCRYPTED="1", BACKUP_RETENTION_DAYS="1", BACKUP_MIN_KEEP="1")
    assert r.returncode == 0 and other.exists()


def _posix_modes_supported(tmp_path) -> bool:
    probe = tmp_path / "mode-probe"
    probe.write_text("x")
    probe.chmod(0o600)
    return (probe.stat().st_mode & 0o777) == 0o600


def test_dump_file_is_not_world_readable(env, tmp_path):
    if not _posix_modes_supported(tmp_path):
        pytest.skip("filesystem does not honour POSIX modes (e.g. NTFS under Git Bash)")
    e, backups, _ = env
    run(BACKUP, e, BACKUP_ALLOW_UNENCRYPTED="1")
    (name,) = dumps(backups)
    mode = (backups / name).stat().st_mode & 0o777
    assert mode & 0o077 == 0, f"dump is group/world accessible: {oct(mode)}"


# --- check_backup_age.sh ------------------------------------------------------------------

def _age_check(e, **extra):
    return subprocess.run([SH, str(CHECK_AGE)], env={**e, **extra}, capture_output=True, text=True, timeout=30)  # noqa: S603


def test_age_check_fails_when_there_is_no_backup(env):
    e, backups, _ = env
    backups.mkdir()
    r = _age_check(e)
    assert r.returncode == 1 and "no encrypted backup" in r.stderr


def test_age_check_passes_for_a_fresh_encrypted_backup(env):
    e, backups, _ = env
    backups.mkdir()
    (backups / "bizboard-20260101T000000Z.sql.gz.gpg").write_bytes(b"x")
    r = _age_check(e)
    assert r.returncode == 0 and r.stdout.startswith("OK")


def test_age_check_fails_when_the_newest_backup_is_older_than_26_hours(env):
    e, backups, _ = env
    backups.mkdir()
    f = backups / "bizboard-20260101T000000Z.sql.gz.age"
    f.write_bytes(b"x")
    _age_of(f, 27 * 3600)
    r = _age_check(e)
    assert r.returncode == 1 and "93600" in r.stderr


def test_age_check_uses_the_newest_file_not_the_oldest(env):
    e, backups, _ = env
    backups.mkdir()
    old, new = backups / "bizboard-1.sql.gz.gpg", backups / "bizboard-2.sql.gz.gpg"
    old.write_bytes(b"x"); new.write_bytes(b"x")
    _age_of(old, 100 * 3600)
    assert _age_check(e).returncode == 0


def test_age_check_ignores_plaintext_dumps_unless_explicitly_allowed(env):
    e, backups, _ = env
    backups.mkdir()
    (backups / "bizboard-20260101T000000Z.sql.gz").write_bytes(b"x")
    assert _age_check(e).returncode == 1, "a plaintext dump must not satisfy the encrypted-backup alert"
    assert _age_check(e, BACKUP_ALLOW_UNENCRYPTED="1").returncode == 0


# --- restore ------------------------------------------------------------------------------

def test_restore_decrypts_gpg_and_feeds_psql(env, tmp_path):
    e, backups, _ = env
    _stub_gpg(tmp_path, e)
    backups.mkdir()
    (backups / "bizboard-20260101T000000Z.sql.gz.gpg").write_bytes(gzip.compress(b"SELECT 42;\n"))
    r = run(RESTORE, e)
    assert r.returncode == 0, r.stderr
    assert (tmp_path / "psql.out").read_text() == "SELECT 42;\n"


def test_restore_picks_the_newest_file_across_formats(env, tmp_path):
    e, backups, _ = env
    _stub_gpg(tmp_path, e)
    backups.mkdir()
    plain = backups / "bizboard-1.sql.gz"
    enc = backups / "bizboard-2.sql.gz.gpg"
    plain.write_bytes(gzip.compress(b"-- old plain\n"))
    enc.write_bytes(gzip.compress(b"-- newer encrypted\n"))
    _age_of(plain, 3600)
    r = run(RESTORE, e)
    assert r.returncode == 0, r.stderr
    assert (tmp_path / "psql.out").read_text() == "-- newer encrypted\n"


def test_restore_with_no_backup_says_so_and_fails(env):
    e, backups, _ = env
    backups.mkdir()
    r = run(RESTORE, e)
    assert r.returncode == 1 and "No backup found" in r.stderr


def test_restore_honours_an_explicit_file(env):
    e, backups, tmp = env
    backups.mkdir()
    newest = backups / "bizboard-9.sql.gz"
    chosen = tmp / "chosen.sql.gz"
    newest.write_bytes(gzip.compress(b"-- newest\n"))
    chosen.write_bytes(gzip.compress(b"-- chosen\n"))
    r = run(RESTORE, e, RESTORE_FILE=chosen.as_posix())
    assert r.returncode == 0 and (tmp / "psql.out").read_text() == "-- chosen\n"


def test_a_failing_decrypt_stops_the_restore_before_psql(env, tmp_path):
    e, backups, _ = env
    _stub_gpg(tmp_path, e)
    backups.mkdir()
    (backups / "bizboard-1.sql.gz.gpg").write_bytes(gzip.compress(b"-- x\n"))
    r = run(RESTORE, e, FAKE_GPG_FAIL="1")
    assert r.returncode != 0 and "Could not read/decrypt" in r.stderr
    assert not (tmp_path / "psql.out").exists()
