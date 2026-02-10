from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.db.models.signals import post_save, post_migrate
from django.dispatch import receiver

User = get_user_model()


@receiver(post_save, sender=User)
def create_or_update_user_profile(sender, instance, created, **kwargs):
    from .models import UserProfile

    if created:
        UserProfile.objects.create(user=instance)
    else:
        UserProfile.objects.get_or_create(user=instance)


@receiver(post_migrate)
def create_scraper_admin_group(sender, **kwargs):
    """
    Create 'scraper_admin' permission group after migrations.
    This group has permissions to manage scraper jobs.
    """
    if sender.name == 'apps.scraper':
        group, created = Group.objects.get_or_create(name='scraper_admin')
        
        if created:
            # Get permissions for scraper app
            try:
                permissions = Permission.objects.filter(
                    content_type__app_label='scraper'
                )
                group.permissions.set(permissions)
            except Exception:
                pass
