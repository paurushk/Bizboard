"""WP-F6 / DIM6-11: the database refuses to commit a posted journal entry that does not balance.

``PostingService.post`` already refuses unbalanced lines. This is the backstop for every other
path (raw SQL, a bulk repair, a bug that edits lines after posting, a DRAFT flipped to POSTED).

Two DEFERRABLE INITIALLY DEFERRED constraint triggers share one check function, so the check
runs at COMMIT, after all of a transaction's lines exist:

- on ``accounting_journalline`` (INSERT / UPDATE / DELETE): checks the old and new entry;
- on ``accounting_journalentry`` (INSERT / UPDATE OF status): catches a posted header with no
  lines and a DRAFT -> POSTED flip that touches no line.

For an entry whose status is POSTED or REVERSED: sum(debit) = sum(credit) and sum(debit) > 0
(every line is one-sided and positive, so a posted entry with no lines sums to 0 and fails).
An entry deleted in the same transaction is skipped. The function is SECURITY DEFINER so its
own read is not hidden by row-level security.

Existing rows are not re-checked by this migration; ``gl.journals_balanced`` and
``gl.no_empty_posted_entries`` find legacy ones for repair (docs/ops/LEDGER_REPAIR_RUNBOOK.md).
PostgreSQL only; a no-op on SQLite.
"""

from django.db import migrations

FORWARD = r"""
CREATE OR REPLACE FUNCTION bizboard_check_journal_entry_balanced(p_entry_id bigint)
RETURNS void
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
  v_status text;
  v_debit numeric;
  v_credit numeric;
BEGIN
  IF p_entry_id IS NULL THEN
    RETURN;
  END IF;
  SELECT status INTO v_status FROM accounting_journalentry WHERE id = p_entry_id;
  IF NOT FOUND OR v_status NOT IN ('POSTED', 'REVERSED') THEN
    RETURN;
  END IF;
  SELECT COALESCE(SUM(debit), 0), COALESCE(SUM(credit), 0)
    INTO v_debit, v_credit
    FROM accounting_journalline WHERE entry_id = p_entry_id;
  IF v_debit <> v_credit THEN
    RAISE EXCEPTION 'journal entry % is % but unbalanced: debit % <> credit %',
      p_entry_id, v_status, v_debit, v_credit
      USING ERRCODE = 'check_violation';
  END IF;
  IF v_debit = 0 THEN
    RAISE EXCEPTION 'journal entry % is % but has no lines', p_entry_id, v_status
      USING ERRCODE = 'check_violation';
  END IF;
END;
$$;

CREATE OR REPLACE FUNCTION bizboard_journalline_balance_trg()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
  IF TG_OP IN ('UPDATE', 'DELETE') THEN
    PERFORM bizboard_check_journal_entry_balanced(OLD.entry_id);
  END IF;
  IF TG_OP IN ('INSERT', 'UPDATE') AND (TG_OP = 'INSERT' OR NEW.entry_id IS DISTINCT FROM OLD.entry_id) THEN
    PERFORM bizboard_check_journal_entry_balanced(NEW.entry_id);
  END IF;
  RETURN NULL;
END;
$$;

CREATE OR REPLACE FUNCTION bizboard_journalentry_balance_trg()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
  PERFORM bizboard_check_journal_entry_balanced(NEW.id);
  RETURN NULL;
END;
$$;

DROP TRIGGER IF EXISTS bizboard_journalline_balanced ON accounting_journalline;
CREATE CONSTRAINT TRIGGER bizboard_journalline_balanced
  AFTER INSERT OR UPDATE OR DELETE ON accounting_journalline
  DEFERRABLE INITIALLY DEFERRED
  FOR EACH ROW EXECUTE FUNCTION bizboard_journalline_balance_trg();

DROP TRIGGER IF EXISTS bizboard_journalentry_balanced ON accounting_journalentry;
CREATE CONSTRAINT TRIGGER bizboard_journalentry_balanced
  AFTER INSERT OR UPDATE OF status ON accounting_journalentry
  DEFERRABLE INITIALLY DEFERRED
  FOR EACH ROW EXECUTE FUNCTION bizboard_journalentry_balance_trg();
"""

BACKWARD = r"""
DROP TRIGGER IF EXISTS bizboard_journalline_balanced ON accounting_journalline;
DROP TRIGGER IF EXISTS bizboard_journalentry_balanced ON accounting_journalentry;
DROP FUNCTION IF EXISTS bizboard_journalline_balance_trg();
DROP FUNCTION IF EXISTS bizboard_journalentry_balance_trg();
DROP FUNCTION IF EXISTS bizboard_check_journal_entry_balanced(bigint);
"""


def forwards(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    with schema_editor.connection.cursor() as cursor:
        cursor.execute(FORWARD)


def backwards(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    with schema_editor.connection.cursor() as cursor:
        cursor.execute(BACKWARD)


class Migration(migrations.Migration):
    dependencies = [
        ("accounting", "0022_expense_status_date_index"),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
