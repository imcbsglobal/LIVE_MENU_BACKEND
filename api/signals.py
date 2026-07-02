import os
from django.db.models.signals import post_delete, pre_save
from django.dispatch import receiver
from .models import MenuItem, Customization, Banner, TVBanner


def delete_file_from_storage(file_field):
    """Safely delete the file from the storage backend."""
    if file_field and hasattr(file_field, 'url'):
        file_field.delete(save=False)


def _guarded_image_update(model, instance, field_names):
    """
    Shared guard used by every pre_save image-cleanup signal.

    - Never touches storage for saves happening on the 'local' SQLite mirror —
      it never holds real files, and the offline cache-warm process saves
      transient instances with blank image fields that must NOT be treated
      as an intentional clear.
    - Only deletes the old file when the incoming value is a genuine NEW
      file replacing it (old_file and new_file both truthy and different).
      A blank/missing incoming value means "untouched", not "cleared".
    """
    if instance._state.db == 'local':
        return
    if not instance.pk:
        return
    try:
        old_instance = model.objects.using(instance._state.db or 'default').get(pk=instance.pk)
    except model.DoesNotExist:
        return
    for field in field_names:
        old_file = getattr(old_instance, field)
        new_file = getattr(instance, field)
        if old_file and new_file and old_file != new_file:
            delete_file_from_storage(old_file)


# -------- MenuItem --------
@receiver(post_delete, sender=MenuItem)
def delete_menuitem_image(sender, instance, **kwargs):
    if instance._state.db == 'local':
        return
    delete_file_from_storage(instance.image)

@receiver(pre_save, sender=MenuItem)
def update_menuitem_image(sender, instance, **kwargs):
    _guarded_image_update(MenuItem, instance, ['image'])


# -------- Banner --------
@receiver(post_delete, sender=Banner)
def delete_banner_image(sender, instance, **kwargs):
    if instance._state.db == 'local':
        return
    delete_file_from_storage(instance.image)

@receiver(pre_save, sender=Banner)
def update_banner_image(sender, instance, **kwargs):
    _guarded_image_update(Banner, instance, ['image'])


# -------- TVBanner --------
@receiver(post_delete, sender=TVBanner)
def delete_tvbanner_image(sender, instance, **kwargs):
    if instance._state.db == 'local':
        return
    delete_file_from_storage(instance.image)

@receiver(pre_save, sender=TVBanner)
def update_tvbanner_image(sender, instance, **kwargs):
    _guarded_image_update(TVBanner, instance, ['image'])


# -------- Customization --------
@receiver(post_delete, sender=Customization)
def delete_customization_files(sender, instance, **kwargs):
    if instance._state.db == 'local':
        return
    delete_file_from_storage(instance.logo)
    delete_file_from_storage(instance.tv_logo)
    delete_file_from_storage(instance.banner)

@receiver(pre_save, sender=Customization)
def update_customization_files(sender, instance, **kwargs):
    _guarded_image_update(Customization, instance, ['logo', 'tv_logo', 'banner'])