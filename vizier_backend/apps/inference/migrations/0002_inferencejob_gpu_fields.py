import django.db.models
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("inference", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="inferencejob",
            name="attempt_count",
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AddField(
            model_name="inferencejob",
            name="gpu_task_arn",
            field=models.CharField(blank=True, max_length=512, null=True),
        ),
        migrations.AddField(
            model_name="inferencejob",
            name="requested_device",
            field=models.CharField(default="cuda", max_length=32),
        ),
        migrations.AddField(
            model_name="inferencejob",
            name="slice_batch_size",
            field=models.PositiveSmallIntegerField(blank=True, null=True),
        ),
        migrations.AddIndex(
            model_name="inferencejob",
            index=django.db.models.Index(
                fields=["requested_device"],
                name="inference_j_request_3ea631_idx",
            ),
        ),
    ]
