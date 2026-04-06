from django.db import migrations, models


class Migration(migrations.Migration):
    """
    Adds tv_theme field to the Customization model.
    Run: python manage.py migrate
    """

    dependencies = [
        # Replace 'api' and '0001_initial' with your actual app label and latest migration
        ('api', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='customization',
            name='tv_theme',
            field=models.CharField(
                max_length=20,
                choices=[
                    ('theme1', 'Dark Card Grid'),
                    ('theme2', 'Cinematic Fullscreen'),
                    ('theme3', 'Elegant Warm Split'),
                ],
                default='theme1',
                blank=True,
                null=True,
                help_text='Which TV display layout/theme to use on the MenuDisplay screen.',
            ),
        ),
    ]