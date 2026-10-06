"""scripts/backup.sh, restore.sh behaviour (F-REL-01).

The scripts are run for real under ``sh`` with stub ``pg_dump`` / ``age`` / ``psql``
binaries on PATH, so the contracts that matter are asserted without a database:

* no encryption recipient  -> fails closed, writes nothing
* pg_dump failure          -> fails, no "successful" backup, no LAST_SUCCESS marker
  (the old ``pg_dump | gzip`` pipeline masked this: /bin/sh has no pipefail)
* offsite command          -> runs with the file as $1; failure is fatal
* retention                -> by age, never below the newest MIN_KEEP files
* restore                  -> refuses a corrupt dump, decrypts .age
"""

from __future__ import annotations

import gzip
import os
import shutil
import subprocess
import time
from pathlib import Path

import pytest

SH = shutil.which("sh")
ROOT = Path(__file__).resolve().parents[2]
BACKUP = ROOT / "scripts" / "backup.sh"
RESTORE = ROOT / "scripts" / "restore.sh"

pytestmark = pytest.mark.skipif(SH is None, reason="needs a POSIX sh")


def _shim(dirpath: Path, name: str, body: str) -> None:
    f = dirpath / name
    f.write_text("#!/bin/sh\n" + body, encoding="utf-8", newline="\n")
    f.chmod(0o755)


def _sh_path(path: Path) -> str:
    """Path form Git Bash searches. ``C:/...`` is skipped for extensionless
    shims when a real ``gpg.exe`` exists later on PATH."""
    posix = path.as_posix()
    if os.name == "nt" and len(posix) > 2 and posix[1] == ":":
        return f"/{posix[0].lower()}{posix[2:]}"
    return posix


@pytest.fixture
def env(tmp_path):
    bindir = tmp_path / "bin"
    bindir.mkdir()
    # pg_dump: emit a tiny SQL script unless told to fail.
    _shim(bindir, "pg_dump", 'if [ "${FAKE_PG_FAIL:-0}" = "1" ]; then echo boom >&2; exit 3; fi\n'
                             'echo "CREATE TABLE t(x int);"\n')
    # age: -r RECIPIENT -o OUT IN   /   -d -i IDENT IN
    _shim(bindir, "age", 'if [ "$1" = "-d" ]; then cat "$4"; exit 0; fi\n'
                         'cp "$5" "$4"\n')
    # psql: record that it was fed SQL.
    _shim(bindir, "psql", 'cat > "$PSQL_SINK"\n')
    backups = tmp_path / "backups"
    e = dict(os.environ)
    e.update({
        "PATH": f"{_sh_path(bindir)}{os.pathsep}{e['PATH']}",
        "BACKUP_DIR": backups.as_posix(),
        "BACKUPS_DIR": backups.as_posix(),
        "POSTGRES_USER": "u",
        "POSTGRES_DB": "d",
        "PSQL_SINK": (tmp_path / "psql.out").as_posix(),
    })
    for k in ("BACKUP_GPG_RECIPIENT", "BACKUP_AGE_RECIPIENT", "BACKUP_ALLOW_UNENCRYPTED",
              "BACKUP_OFFSITE_CMD", "BACKUP_REQUIRE_OFFSITE", "FAKE_PG_FAIL", "RESTORE_FILE"):
        e.pop(k, None)
    return e, backups, tmp_path


def run(script, e, **extra):
    return subprocess.run([SH, str(script)], env={**e, **extra}, capture_output=True, text=True, timeout=60)  # noqa: S603 - fixed shell + repo script


def dumps(backups):
    return sorted(p.name for p in backups.glob("bizboard-*")) if backups.exists() else []


def test_fails_closed_without_recipient(env):
    e, backups, _ = env
    r = run(BACKUP, e)
    assert r.returncode != 0
    assert "Refusing to write a plaintext dump" in r.stderr
    assert dumps(backups) == []
    assert not (backups / "LAST_SUCCESS").exists()


def test_pg_dump_failure_is_fatal_and_leaves_nothing(env):
    e, backups, _ = env
    r = run(BACKUP, e, BACKUP_ALLOW_UNENCRYPTED="1", FAKE_PG_FAIL="1")
    assert r.returncode != 0
    assert "pg_dump exited non-zero" in r.stderr
    assert dumps(backups) == []
    assert not (backups / "LAST_SUCCESS").exists()
    assert not list(backups.glob(".bizboard-*")), "partial files must be cleaned up"


def test_plain_dump_when_explicitly_allowed(env):
    e, backups, _ = env
    r = run(BACKUP, e, BACKUP_ALLOW_UNENCRYPTED="1")
    assert r.returncode == 0, r.stderr
    (name,) = dumps(backups)
    assert name.endswith(".sql.gz")
    assert b"CREATE TABLE" in gzip.decompress((backups / name).read_bytes())
    assert (backups / "LAST_SUCCESS").read_text().split()[1] == name
    assert "UNENCRYPTED" in r.stderr and "this host only" in r.stderr


def test_encrypted_dump_uses_age_and_is_not_plaintext_named(env):
    e, backups, _ = env
    r = run(BACKUP, e, BACKUP_AGE_RECIPIENT="age1xyz")
    assert r.returncode == 0, r.stderr
    (name,) = dumps(backups)
    assert name.endswith(".sql.gz.age")


def test_offsite_command_receives_the_file_and_failure_is_fatal(env):
    e, backups, tmp = env
    sink = tmp / "offsite.txt"
    ok = run(BACKUP, e, BACKUP_ALLOW_UNENCRYPTED="1",
             BACKUP_OFFSITE_CMD=f'echo "$1" > {sink.as_posix()}')
    assert ok.returncode == 0, ok.stderr
    assert sink.read_text().strip().endswith(".sql.gz")

    shutil.rmtree(backups)
    bad = run(BACKUP, e, BACKUP_ALLOW_UNENCRYPTED="1", BACKUP_OFFSITE_CMD="exit 7")
    assert bad.returncode != 0
    assert "offsite copy command failed" in bad.stderr
    assert not (backups / "LAST_SUCCESS").exists(), "a failed offsite copy must not mark success"


def test_require_offsite_without_command_fails(env):
    e, backups, _ = env
    r = run(BACKUP, e, BACKUP_ALLOW_UNENCRYPTED="1", BACKUP_REQUIRE_OFFSITE="1")
    assert r.returncode != 0
    assert "BACKUP_OFFSITE_CMD is not set" in r.stderr
    assert not (backups / "LAST_SUCCESS").exists()


def test_retention_is_by_age_but_keeps_the_newest_min_keep(env):
    e, backups, _ = env
    backups.mkdir()
    old = time.time() - 90 * 86400
    for i in range(10):
        f = backups / f"bizboard-2020010{i}T000000Z.sql.gz"
        f.write_bytes(gzip.compress(b"x"))
        os.utime(f, (old - i, old - i))  # all 90 days old; i=0 is the newest of the old ones
    r = run(BACKUP, e, BACKUP_ALLOW_UNENCRYPTED="1", BACKUP_RETENTION_DAYS="30", BACKUP_MIN_KEEP="3")
    assert r.returncode == 0, r.stderr
    left = dumps(backups)
    assert len(left) == 3, left          # new dump + the 2 newest old ones
    assert any(n.startswith("bizboard-2020010") for n in left)


def test_recent_files_are_kept_even_beyond_min_keep(env):
    e, backups, _ = env
    backups.mkdir()
    for i in range(5):
        (backups / f"bizboard-2099010{i}T000000Z.sql.gz").write_bytes(gzip.compress(b"x"))
    r = run(BACKUP, e, BACKUP_ALLOW_UNENCRYPTED="1", BACKUP_RETENTION_DAYS="30", BACKUP_MIN_KEEP="1")
    assert r.returncode == 0, r.stderr
    assert len(dumps(backups)) == 6, "files younger than the retention window must never be pruned"


AGE = ROOT / "scripts" / "check_backup_age.sh"


def test_fresh_encrypted_dump_passes_without_reading_last_success(env):
    e, backups, _ = env
    backups.mkdir()
    (backups / "bizboard-20260101T000000Z.sql.gz.age").write_bytes(b"age")
    (backups / "LAST_SUCCESS").write_text("ancient missing-file\n")
    r = run(AGE, e)
    assert r.returncode == 0, r.stderr + r.stdout


def test_old_encrypted_dump_fails_even_when_last_success_is_new(env):
    e, backups, _ = env
    backups.mkdir()
    old_file = backups / "bizboard-20200101T000000Z.sql.gz.gpg"
    old_file.write_bytes(b"gpg")
    old = time.time() - 100000
    os.utime(old_file, (old, old))
    (backups / "LAST_SUCCESS").write_text(f"{int(time.time())} {old_file.name}\n")
    r = run(AGE, e)
    assert r.returncode == 1
    assert "93600" in r.stderr


def test_plaintext_dump_is_ignored_unless_explicitly_allowed(env):
    e, backups, _ = env
    backups.mkdir()
    (backups / "bizboard-20260101T000000Z.sql.gz").write_bytes(gzip.compress(b"x"))
    missing = run(AGE, e)
    assert missing.returncode == 1
    allowed = run(AGE, e, BACKUP_ALLOW_UNENCRYPTED="1")
    assert allowed.returncode == 0, allowed.stderr


def test_restore_refuses_a_corrupt_dump(env):
    e, backups, tmp = env
    backups.mkdir()
    bad = backups / "bizboard-20260101T000000Z.sql.gz"
    bad.write_bytes(b"not gzip at all")
    r = run(RESTORE, e)
    assert r.returncode != 0
    assert "integrity test" in r.stderr
    assert not (tmp / "psql.out").exists() or (tmp / "psql.out").read_text() == ""


def test_restore_decrypts_age_and_feeds_psql(env):
    e, backups, tmp = env
    backups.mkdir()
    (backups / "bizboard-20260101T000000Z.sql.gz.age").write_bytes(gzip.compress(b"SELECT 1;\n"))
    ident = tmp / "id.txt"
    ident.write_text("AGE-SECRET-KEY-FAKE")
    r = run(RESTORE, e, RESTORE_AGE_IDENTITY=ident.as_posix())
    assert r.returncode == 0, r.stderr
    assert (tmp / "psql.out").read_text() == "SELECT 1;\n"


def test_restore_age_without_identity_fails(env):
    e, backups, _ = env
    backups.mkdir()
    (backups / "bizboard-20260101T000000Z.sql.gz.age").write_bytes(gzip.compress(b"x"))
    r = run(RESTORE, e)
    assert r.returncode != 0
    assert "RESTORE_AGE_IDENTITY" in r.stderr
