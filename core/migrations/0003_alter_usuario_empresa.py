from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0002_alter_ordemservico_anexo_alter_usuario_groups_and_more'),
    ]

    operations = [
        migrations.AlterField(
            model_name='usuario',
            name='empresa',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='usuarios', to='core.empresa'),
        ),
    ]
