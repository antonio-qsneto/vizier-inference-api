from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("audit", "0001_initial"),
    ]

    operations = [
        migrations.AlterField(
            model_name="auditlog",
            name="action",
            field=models.CharField(
                choices=[
                    ("LOGIN_SEEN", "Login Seen"),
                    ("STUDY_SUBMIT", "Study Submitted"),
                    ("STUDY_STATUS_CHECK", "Study Status Checked"),
                    ("RESULT_DOWNLOAD", "Result Downloaded"),
                    ("DOCTOR_INVITE", "Doctor Invited"),
                    ("DOCTOR_INVITE_CANCEL", "Doctor Invitation Canceled"),
                    ("DOCTOR_REMOVE", "Doctor Removed"),
                    ("CLINIC_CREATED", "Clinic Created"),
                    ("CLINIC_UPDATED", "Clinic Updated"),
                ],
                max_length=50,
            ),
        ),
    ]
