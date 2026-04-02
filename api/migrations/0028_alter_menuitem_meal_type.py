import json
from django.db import migrations, models


def clean_meal_type_forward(apps, schema_editor):
    """
    Convert existing meal_type CharField values to valid JSON lists
    before altering the column to JSONField.
    
    Old values seen in DB:
      ''       -> []
      'all'    -> []
      '1'      -> ['1']
      '2'      -> ['2']
      '["1"]'  -> ['1']   (already JSON string)
    """
    db_alias = schema_editor.connection.alias
    MenuItem = apps.get_model('api', 'MenuItem')

    for item in MenuItem.objects.using(db_alias).all():
        raw = item.meal_type or ''
        raw = raw.strip()

        # Already a valid JSON list string?
        if raw.startswith('['):
            try:
                parsed = json.loads(raw)
                # keep only non-empty, non-null string IDs
                clean = [str(x) for x in parsed if x and str(x).strip() not in ('', 'null', 'all')]
                item.meal_type = json.dumps(clean)
                item.save(update_fields=['meal_type'])
                continue
            except Exception:
                pass

        # Invalid or empty values → empty list
        if not raw or raw in ('all', 'null', 'none', '0'):
            item.meal_type = '[]'
        else:
            # Single numeric ID string e.g. "1"
            item.meal_type = json.dumps([raw])

        item.save(update_fields=['meal_type'])


def clean_meal_type_backward(apps, schema_editor):
    """Reverse: convert JSON list back to first ID string (best-effort)."""
    db_alias = schema_editor.connection.alias
    MenuItem = apps.get_model('api', 'MenuItem')

    for item in MenuItem.objects.using(db_alias).all():
        raw = item.meal_type or '[]'
        try:
            parsed = json.loads(raw)
            item.meal_type = str(parsed[0]) if parsed else ''
        except Exception:
            item.meal_type = ''
        item.save(update_fields=['meal_type'])


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0027_remove_appuser_staff_role_appuser_role_and_more'),
    ]

    operations = [
        # Step 1: clean existing data while still a CharField
        migrations.RunPython(clean_meal_type_forward, clean_meal_type_backward),

        # Step 2: alter column to JSONField
        migrations.AlterField(
            model_name='menuitem',
            name='meal_type',
            field=models.JSONField(
                blank=True,
                default=list,
                help_text='List of MealType IDs. Empty list = shown all day.'
            ),
        ),
    ]