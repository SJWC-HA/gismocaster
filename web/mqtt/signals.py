# https://simpleisbetterthancomplex.com/tutorial/2016/07/28/how-to-create-django-signals.html
from .models import Setting
from tuya.models import Gismo, GismoModel, Dp, DpName, HAOverwrite
from homeassistant.models import Component, Topic, TopicValue, Template, ComponentValue
from django.db.models.signals import post_save, post_delete, pre_save, pre_delete
from django.dispatch import receiver
from . import mqtt


@receiver(pre_save, sender=Gismo)
def pre_save_gismo(sender, instance, **kwargs):
    mqtt.unpublish_gismo(instance)


@receiver(post_save, sender=Gismo)
def save_gismo(sender, instance, **kwargs):
    mqtt.publish_gismo(instance)


@receiver(pre_delete, sender=Gismo)
def delete_gismo(sender, instance, using, **kwargs):
    mqtt.unpublish_gismo(instance)


@receiver(post_save, sender=HAOverwrite)
def save_dps(sender, instance, **kwargs):
    mqtt.publish_gismos()


@receiver(pre_delete, sender=HAOverwrite)
def delete_dps(sender, instance, using, **kwargs):
    mqtt.publish_gismos()


@receiver(post_save, sender=Dp)
def save_dps(sender, instance, **kwargs):
    mqtt.publish_gismos()


@receiver(pre_delete, sender=Dp)
def delete_dps(sender, instance, using, **kwargs):
    mqtt.publish_gismos()


@receiver(post_save, sender=Setting)
def save_setting(sender, instance, **kwargs):
    mqtt.init()


@receiver(pre_delete, sender=Setting)
def delete_setting(sender, instance, using, **kwargs):
    mqtt.init()


# HA transformers
@receiver(post_save, sender=Component)
def save_component(sender, instance, **kwargs):
    mqtt.publish_transformers()


@receiver(post_save, sender=ComponentValue)
def save_cvalue(sender, instance, **kwargs):
    mqtt.publish_transformers()


@receiver(post_save, sender=Topic)
def save_topic(sender, instance, **kwargs):
    mqtt.publish_transformers()


@receiver(post_save, sender=TopicValue)
def save_tvalue(sender, instance, **kwargs):
    mqtt.publish_transformers()


@receiver(post_save, sender=Template)
def save_template(sender, instance, **kwargs):
    mqtt.publish_transformers()
