"""Connect to MQTT and send retain messages."""
import logging
import json
import paho.mqtt.client as mqtt
from homeassistant.models import Component
from .models import Setting, Gismo, Dp, HAOverwrite


LOGLEVEL = logging.INFO
LOGGER = logging.getLogger(__name__)
logging.basicConfig(
    format="%(asctime)s %(levelname)-8s [%(name)s] %(message)s", level=LOGLEVEL
)

MQTT_CLIENT = None
MQTT_CONNECTED = None


def _connack_string(state):

    states = [
        "Connection successful",
        "Connection refused - incorrect protocol version",
        "Connection refused - invalid client identifier",
        "Connection refused - server unavailable",
        "Connection refused - bad username or password",
        "Connection refused - not authorised",
    ]
    return states[state]


# TODO what are the types of these func params
def on_connect(client, userdata, flags, rc):
    """MQTT connection callback.

    Runs in MQTT scope
    """
    global MQTT_CONNECTED, MQTT_CLIENT
    MQTT_CLIENT = client
    LOGGER.info("MQTT Connection state: %s " % (_connack_string(rc)))
    MQTT_CONNECTED = True
    publish_gismos()
    # MQTT_CLIENT.subscribe("homeassistant/#")


# TODO what are the types of these func params
# def on_message(client, userdata, message):

#     LOGGER.debug(
#         "topic %s retained %s message received %s",
#         message.topic,
#         message.retain,
#         str(message.payload.decode("utf-8")),
#     )


def _publish(topic: str, payload_dict: dict, clear: bool = False, retain: bool = True):

    # global MQTT_CLIENT
    if not MQTT_CONNECTED:
        _mqtt_connect()

    payload = json.dumps(payload_dict)
    if clear:
        payload = None

    try:
        LOGGER.debug(f"_publish {topic} {payload}")
        MQTT_CLIENT.publish(topic, payload, retain=retain)
    except Exception as ex:
        LOGGER.exception(f"_publish {ex}", exc_info=False)


def _filter_id(dict_dirty: dict):
    """Remove id fields from resultset."""
    return dict(
        filter(
            lambda elem: elem[0][-3:] != "_id" and elem[0] != "id", dict_dirty.items()
        )
    )


def _cast_type(type_value: str, value: str):

    if type_value == "bool":
        return bool(value)
    if type_value == "int":
        return int(value)
    if type_value == "float":
        return float(value)
    return value


def _set_device(payload_dict: dict, gismo_dict: dict, name: str):

    payload_dict["device"] = {
        "identifiers": [gismo_dict["deviceid"]],
        "name": name,
        "model": f"Tuya",
        "sw_version": "1.0.0",
        "manufacturer": "GismoCaster",
        "via_device": gismo_dict["name"],
    }


def _publish_hass_dp(gismo: dict, dp: dict, clear: bool = False):
    """Send retain message for Home Assistant config to broker."""
    # get the gismo
    gismo_dict = dict(Gismo.objects.filter(id=gismo.id).values()[0])

    # get defaults for ha component
    ha_component = Component.objects.get(id=dp["ha_component_id"])
    ha_vars_list = list(ha_component.variables.all().values())
    payload_dict = {}

    for item in ha_vars_list:
        if not item["default_value"]:
            continue
        payload_dict[item["abbreviation"]] = _cast_type(
            item["type_value"], item["default_value"]
        )

    # get ha overwrites
    ha_overwrites = HAOverwrite.objects.filter(dp_id=dp["id"]).all()
    for ha_overwrite in ha_overwrites:
        payload_dict[ha_overwrite.variable.abbreviation] = _cast_type(
            ha_overwrite.variable.type_value, ha_overwrite.value
        )

    hass_id = f'{gismo_dict["deviceid"]}_{dp["key"]}'

    topic = f"homeassistant/{ha_component.technical_name}/{hass_id}/config"

    if "name" in payload_dict:
        payload_dict["name"] = dp["name"]

    payload_dict["uniq_id"] = hass_id

    _set_device(payload_dict, gismo_dict, dp["name"])

    payload_dict["~"] = f'tuya/{gismo_dict["deviceid"]}/{dp["key"]}/'
    if "avty_t" in payload_dict:
        payload_dict["avty_t"] = payload_dict["avty_t"].replace(
            "~", f'tuya/{gismo_dict["deviceid"]}/'
        )

    _publish(topic, payload_dict, clear)


def _publish_hass(gismo, clear: bool = False):
    """Send retain messages for Home Assistant config to broker."""
    # send sensor with primary name
    # get the gismo
    # gismo_dict = dict(Gismo.objects.filter(id=gismo.id).values()[0])
    # topic = f"homeassistant/sensor/{gismo_dict['deviceid']}_status/config"
    # payload_dict = {
    #     "name": f"{gismo_dict['name']}",
    #     "uniq_id": f'{gismo_dict["deviceid"]}_status',
    # }
    # _set_device(payload_dict, gismo_dict, gismo_dict['name'])
    # _publish(topic, payload_dict, clear)

    # get the dps
    dps = list(Dp.objects.filter(gismo_id=gismo.id).values())

    for dp in dps:
        _publish_hass_dp(gismo, dp, clear)


def publish_gismo(gismo, clear: bool = False):
    """Send retain message for TuyaMQTT config to broker."""
    if not MQTT_CONNECTED:
        _mqtt_connect()

    # get the device
    payload_dict = _filter_id(dict(Gismo.objects.filter(id=gismo.id).values()[0]))

    # get the dps
    dps = Dp.objects.filter(gismo_id=gismo.id)

    payload_dict["dps"] = list(map(_filter_id, list(dps.values())))

    topic = f"tuya/discovery/{payload_dict['deviceid']}"

    clear_tuya = clear
    if not gismo.tuya_discovery:
        clear_tuya = True
    _publish(topic, payload_dict, clear_tuya)

    clear_hass = clear
    if not gismo.ha_discovery:
        clear_hass = True
    _publish_hass(gismo, clear_hass)


def unpublish_gismo(gismo):
    """Remove the device from MQTT."""
    if not MQTT_CONNECTED:
        _mqtt_connect()
    publish_gismo(gismo, True)


def publish_gismos():
    """Add the device to MQTT."""
    if not MQTT_CONNECTED:
        _mqtt_connect()

    for gismo in Gismo.objects.all():
        publish_gismo(gismo)


def _mqtt_connect():
    """Connect to MQTT Broker."""
    # global client
    try:
        MQTT_CLIENT = mqtt.Client()
        MQTT_CLIENT.enable_logger()

        user = Setting.objects.get(name="mqtt_user").value
        passwd = Setting.objects.get(name="mqtt_pass").value
        if user and passwd:
            MQTT_CLIENT.username_pw_set(
                user, passwd,
            )

        host = Setting.objects.get(name="mqtt_host").value
        if not host:
            host = "127.0.0.1"
        port = int(Setting.objects.get(name="mqtt_port").value)
        if not port:
            port = 1883
        MQTT_CLIENT.connect(
            host, port, 60,
        )
        MQTT_CLIENT.on_connect = on_connect
        MQTT_CLIENT.loop_start()
        # MQTT_CLIENT.on_message = on_message

    except Exception as ex:
        LOGGER.warning("(%s) Failed to connect to MQTT Broker %s", "", ex)


def init():
    """Start the MQTT connection."""
    _mqtt_connect()


"""
14:29:19 MQT: homeassistant/light/CAA3EA_LI_4/config =  (retained)
14:29:19 MQT: homeassistant/switch/CAA3EA_RL_4/config = {"name":"IR Zone 4","cmd_t":"~cmnd/POWER4","stat_t":"~tele/STATE","val_tpl":"{{value_json.POWER4}}","pl_off":"OFF","pl_on":"ON","avty_t":"~tele/LWT","pl_avail":"Online","pl_not_avail":"Offline","uniq_id":"CAA3EA_RL_4","device":{"identifiers":["CAA3EA"],"connections":[["mac","60:01:94:CA:A3:EA"]]},"~":"sonoff/"} (retained)
14:29:19 MQT: homeassistant/light/CAA3EA_LI_5/config =  (retained)
14:29:19 MQT: homeassistant/switch/CAA3EA_RL_5/config =  (retained)
14:29:19 MQT: homeassistant/light/CAA3EA_LI_6/config =  (retained)
14:29:19 MQT: homeassistant/switch/CAA3EA_RL_6/config =  (retained)
14:29:19 MQT: homeassistant/light/CAA3EA_LI_7/config =  (retained)
14:29:19 MQT: homeassistant/switch/CAA3EA_RL_7/config =  (retained)
14:29:19 MQT: homeassistant/light/CAA3EA_LI_8/config =  (retained)
14:29:19 MQT: homeassistant/switch/CAA3EA_RL_8/config =  (retained)
14:29:21 MQT: homeassistant/binary_sensor/CAA3EA_BTN_1/config = {"name":"IR Zone Button1","stat_t":"~stat/BUTTON1","avty_t":"~tele/LWT","pl_avail":"Online","pl_not_avail":"Offline","uniq_id":"CAA3EA_BTN_1","device":{"identifiers":["CAA3EA"],"connections":[["mac","60:01:94:CA:A3:EA"]]},"~":"sonoff/","value_template":"{{value_json.STATE}}","pl_on":"TOGGLE","off_delay":1} (retained)
14:29:21 MQT: homeassistant/binary_sensor/CAA3EA_BTN_2/config = {"name":"IR Zone Button2","stat_t":"~stat/BUTTON2","avty_t":"~tele/LWT","pl_avail":"Online","pl_not_avail":"Offline","uniq_id":"CAA3EA_BTN_2","device":{"identifiers":["CAA3EA"],"connections":[["mac","60:01:94:CA:A3:EA"]]},"~":"sonoff/","value_template":"{{value_json.STATE}}","pl_on":"TOGGLE","off_delay":1} (retained)
14:29:21 MQT: homeassistant/binary_sensor/CAA3EA_BTN_3/config = {"name":"IR Zone Button3","stat_t":"~stat/BUTTON3","avty_t":"~tele/LWT","pl_avail":"Online","pl_not_avail":"Offline","uniq_id":"CAA3EA_BTN_3","device":{"identifiers":["CAA3EA"],"connections":[["mac","60:01:94:CA:A3:EA"]]},"~":"sonoff/","value_template":"{{value_json.STATE}}","pl_on":"TOGGLE","off_delay":1} (retained)
14:29:21 MQT: homeassistant/binary_sensor/CAA3EA_BTN_4/config = {"name":"IR Zone Button4","stat_t":"~stat/BUTTON4","avty_t":"~tele/LWT","pl_avail":"Online","pl_not_avail":"Offline","uniq_id":"CAA3EA_BTN_4","device":{"identifiers":["CAA3EA"],"connections":[["mac","60:01:94:CA:A3:EA"]]},"~":"sonoff/","value_template":"{{value_json.STATE}}","pl_on":"TOGGLE","off_delay":1} (retained)
14:29:21 MQT: homeassistant/binary_sensor/CAA3EA_SW_1/config =  (retained)
14:29:21 MQT: homeassistant/binary_sensor/CAA3EA_SW_2/config =  (retained)
14:29:21 MQT: homeassistant/binary_sensor/CAA3EA_SW_3/config =  (retained)
14:29:21 MQT: homeassistant/binary_sensor/CAA3EA_SW_4/config =  (retained)
14:29:21 MQT: homeassistant/binary_sensor/CAA3EA_SW_5/config =  (retained)
14:29:21 MQT: homeassistant/binary_sensor/CAA3EA_SW_6/config =  (retained)
14:29:21 MQT: homeassistant/binary_sensor/CAA3EA_SW_7/config =  (retained)
14:29:21 MQT: homeassistant/binary_sensor/CAA3EA_SW_8/config =  (retained)
14:29:21 MQT: homeassistant/sensor/CAA3EA_status/config = {"name":"IR Zone status","stat_t":"~HASS_STATE","avty_t":"~LWT","frc_upd":true,"pl_avail":"Online","pl_not_avail":"Offline","json_attributes_topic":"~HASS_STATE","unit_of_meas":" ","val_tpl":"{{value_json['RSSI']}}","ic":"mdi:information-outline","uniq_id":"CAA3EA_status","device":{"identifiers":["CAA3EA"],"connections":[["mac","60:01:94:CA:A3:EA"]],"name":"IR Zone","model":"Sonoff 4CH Pro","sw_version":"8.1.0.2(1e06976-tasmota)","manufacturer":"Tasmota"},"~":"sonoff/tele/"} (retained)
14:29:22 MQT: sonoff/tele/STATE = {"Time":"2020-06-01T14:29:22","Uptime":"0T00:00:12","UptimeSec":12,"Heap":27,"SleepMode":"Dynamic","Sleep":50,"LoadAvg":97,"MqttCount":1,"POWER1":"OFF","POWER2":"OFF","POWER3":"OFF","POWER4":"OFF","Wifi":{"AP":1,"SSId":"VFNL-C88C58","BSSId":"00:1D:AA:C8:8C:58","Channel":9,"RSSI":100,"Signal":-23,"LinkCount":1,"Downtime":"0T00:00:06"}}
"""
