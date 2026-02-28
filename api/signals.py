import os
from django.db.models.signals import post_delete, pre_save
from django.dispatch import receiver
from .models import MenuItem, Customization, Banner, TVBanner

def delete_file_from_storage(file_field):
    """Safely delete the file from the storage backend."""
    if file_field and hasattr(file_field, 'url'):
        file_field.delete(save=False)

# -------- MenuItem --------
@receiver(post_delete, sender=MenuItem)
def delete_menuitem_image(sender, instance, **kwargs):
    delete_file_from_storage(instance.image)

@receiver(pre_save, sender=MenuItem)
def update_menuitem_image(sender, instance, **kwargs):
    if not instance.pk:
        return
    try:
        old_file = MenuItem.objects.get(pk=instance.pk).image
    except MenuItem.DoesNotExist:
        return
    new_file = instance.image
    if old_file and old_file != new_file:
        delete_file_from_storage(old_file)

# -------- Banner --------
@receiver(post_delete, sender=Banner)
def delete_banner_image(sender, instance, **kwargs):
    delete_file_from_storage(instance.image)

@receiver(pre_save, sender=Banner)
def update_banner_image(sender, instance, **kwargs):
    if not instance.pk:
        return
    try:
        old_file = Banner.objects.get(pk=instance.pk).image
    except Banner.DoesNotExist:
        return
    new_file = instance.image
    if old_file and old_file != new_file:
        delete_file_from_storage(old_file)

# -------- TVBanner --------
@receiver(post_delete, sender=TVBanner)
def delete_tvbanner_image(sender, instance, **kwargs):
    delete_file_from_storage(instance.image)

@receiver(pre_save, sender=TVBanner)
def update_tvbanner_image(sender, instance, **kwargs):
    if not instance.pk:
        return
    try:
        old_file = TVBanner.objects.get(pk=instance.pk).image
    except TVBanner.DoesNotExist:
        return
    new_file = instance.image
    if old_file and old_file != new_file:
        delete_file_from_storage(old_file)

# -------- Customization --------
@receiver(post_delete, sender=Customization)
def delete_customization_files(sender, instance, **kwargs):
    delete_file_from_storage(instance.logo)
    delete_file_from_storage(instance.tv_logo)
    delete_file_from_storage(instance.banner)

@receiver(pre_save, sender=Customization)
def update_customization_files(sender, instance, **kwargs):
    if not instance.pk:
        return
    try:
        old_instance = Customization.objects.get(pk=instance.pk)
    except Customization.DoesNotExist:
        return
        
    if old_instance.logo and old_instance.logo != instance.logo:
        delete_file_from_storage(old_instance.logo)
    if old_instance.tv_logo and old_instance.tv_logo != instance.tv_logo:
        delete_file_from_storage(old_instance.tv_logo)
    if old_instance.banner and old_instance.banner != instance.banner:
        delete_file_from_storage(old_instance.banner)
