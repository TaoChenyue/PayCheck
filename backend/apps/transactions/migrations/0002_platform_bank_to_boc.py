# Generated manually for Phase 3: align PLATFORM_CHOICES with design

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("transactions", "0001_initial"),
    ]

    operations = [
        migrations.AlterField(
            model_name="transaction",
            name="platform",
            field=models.CharField(
                choices=[("alipay", "支付宝"), ("wechat", "微信"), ("boc", "银行")],
                max_length=20,
            ),
        ),
    ]
