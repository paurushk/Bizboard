from django.db import migrations


def forwards(apps, schema_editor):
    JournalEntry = apps.get_model("accounting", "JournalEntry")
    JournalEntry.objects.filter(source_type="PayRun").update(source_type="PAY_RUN")


def backwards(apps, schema_editor):
    JournalEntry = apps.get_model("accounting", "JournalEntry")
    JournalEntry.objects.filter(source_type="PAY_RUN").update(source_type="PayRun")


class Migration(migrations.Migration):
    """ACC-08: normalise the payroll GL source_type to SCREAMING_SNAKE
    (``PAY_RUN``) so the books-health missing-posting check and every other
    source_type consumer follow one convention."""

    dependencies = [
        ("accounting", "0008_w0_01_gl_duplicate_hygiene"),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
