from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

from apps.accounts.models import UserProfile

User = get_user_model()


class Command(BaseCommand):
    help = "Create a superuser with admin profile (idempotent)."

    def add_arguments(self, parser):
        parser.add_argument("--username", default="admin")
        parser.add_argument("--email", default="admin@sssys.local")
        parser.add_argument("--password", default="admin")

    def handle(self, *args, **options):
        username = options["username"]
        if User.objects.filter(username=username).exists():
            self.stdout.write(self.style.WARNING(f"User '{username}' already exists."))
            user = User.objects.get(username=username)
        else:
            user = User.objects.create_superuser(
                username=username,
                email=options["email"],
                password=options["password"],
            )
            self.stdout.write(self.style.SUCCESS(f"Superuser '{username}' created."))

        profile = user.profile
        profile.role = UserProfile.ROLE_ADMIN
        profile.save()
        self.stdout.write(self.style.SUCCESS("Profile role set to admin."))
